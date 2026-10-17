-- Gradebook schema with Row Level Security.
--
-- Every row is reachable from exactly one teacher, and every policy checks
-- that the teacher is auth.uid(). The API connects as `postgres`, then runs
-- `SET LOCAL ROLE authenticated` and sets `request.jwt.claims` for each
-- request transaction, so these policies apply to API traffic the same way
-- they apply to supabase-js clients.

create extension if not exists "pgcrypto";

create type grade_status as enum ('graded', 'missing', 'excused', 'late');

-- teachers ------------------------------------------------------------------

create table teachers (
    id         uuid primary key references auth.users (id) on delete cascade,
    name       text not null default '',
    created_at timestamptz not null default now()
);

-- Create a teacher row when someone signs up through Supabase Auth.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
    insert into public.teachers (id, name)
    values (new.id, coalesce(new.raw_user_meta_data ->> 'name', ''))
    on conflict (id) do nothing;
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- courses -------------------------------------------------------------------

create table courses (
    id         uuid primary key default gen_random_uuid(),
    teacher_id uuid not null default auth.uid() references teachers (id) on delete cascade,
    name       text not null,
    term       text not null default '',
    created_at timestamptz not null default now()
);
create index courses_teacher_id_idx on courses (teacher_id);

-- students ------------------------------------------------------------------
-- Students are owned by a teacher so a roster can exist before enrollment
-- and so RLS has something to check. The same email may appear under
-- different teachers.

create table students (
    id         uuid primary key default gen_random_uuid(),
    teacher_id uuid not null default auth.uid() references teachers (id) on delete cascade,
    name       text not null,
    email      text,
    created_at timestamptz not null default now(),
    unique (teacher_id, email)
);
create index students_teacher_id_idx on students (teacher_id);

-- enrollments ---------------------------------------------------------------

create table enrollments (
    course_id  uuid not null references courses (id) on delete cascade,
    student_id uuid not null references students (id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (course_id, student_id)
);
create index enrollments_student_id_idx on enrollments (student_id);

-- categories ----------------------------------------------------------------

create table categories (
    id          uuid primary key default gen_random_uuid(),
    course_id   uuid not null references courses (id) on delete cascade,
    name        text not null,
    weight      numeric(6, 3) not null check (weight >= 0),
    drop_lowest integer not null default 0 check (drop_lowest >= 0),
    unique (course_id, name),
    -- Lets assignments reference (id, course_id) so an assignment can never
    -- point at another course's category.
    unique (id, course_id)
);

-- assignments ---------------------------------------------------------------

create table assignments (
    id              uuid primary key default gen_random_uuid(),
    course_id       uuid not null references courses (id) on delete cascade,
    category_id     uuid not null,
    title           text not null,
    points_possible numeric(8, 2) not null check (points_possible > 0),
    due_date        date,
    created_at      timestamptz not null default now(),
    foreign key (category_id, course_id) references categories (id, course_id) on delete cascade
);
create index assignments_course_id_idx on assignments (course_id);

-- grades --------------------------------------------------------------------

create table grades (
    assignment_id uuid not null references assignments (id) on delete cascade,
    student_id    uuid not null references students (id) on delete cascade,
    score         numeric(8, 2) check (score >= 0),
    status        grade_status not null default 'graded',
    updated_at    timestamptz not null default now(),
    primary key (assignment_id, student_id),
    -- A graded or late item needs a score. Missing and excused may omit it.
    check (status in ('missing', 'excused') or score is not null)
);
create index grades_student_id_idx on grades (student_id);

-- Row Level Security --------------------------------------------------------

alter table teachers    enable row level security;
alter table courses     enable row level security;
alter table students    enable row level security;
alter table enrollments enable row level security;
alter table categories  enable row level security;
alter table assignments enable row level security;
alter table grades      enable row level security;

create function public.owns_course(cid uuid) returns boolean
language sql stable security invoker set search_path = public as $$
    select exists (select 1 from courses where id = cid and teacher_id = auth.uid());
$$;

create policy "teachers: self" on teachers
    for all to authenticated
    using (id = auth.uid()) with check (id = auth.uid());

create policy "courses: owner" on courses
    for all to authenticated
    using (teacher_id = auth.uid()) with check (teacher_id = auth.uid());

create policy "students: owner" on students
    for all to authenticated
    using (teacher_id = auth.uid()) with check (teacher_id = auth.uid());

create policy "enrollments: course owner" on enrollments
    for all to authenticated
    using (owns_course(course_id))
    with check (
        owns_course(course_id)
        and exists (select 1 from students s where s.id = student_id and s.teacher_id = auth.uid())
    );

create policy "categories: course owner" on categories
    for all to authenticated
    using (owns_course(course_id)) with check (owns_course(course_id));

create policy "assignments: course owner" on assignments
    for all to authenticated
    using (owns_course(course_id)) with check (owns_course(course_id));

create policy "grades: course owner" on grades
    for all to authenticated
    using (exists (
        select 1 from assignments a where a.id = assignment_id and owns_course(a.course_id)
    ))
    with check (exists (
        select 1 from assignments a
        join enrollments e on e.course_id = a.course_id and e.student_id = grades.student_id
        where a.id = assignment_id and owns_course(a.course_id)
    ));

grant usage on schema public to authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;
