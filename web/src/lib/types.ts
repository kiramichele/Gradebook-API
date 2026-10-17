// Friendly names for the generated API types. Regenerate with `npm run gen:api`.
import type { components } from "./api-schema";

type Schemas = components["schemas"];

export type Teacher = Schemas["TeacherRead"];
export type Course = Schemas["CourseRead"];
export type CourseCreate = Schemas["CourseCreate"];
export type CourseUpdate = Schemas["CourseUpdate"];
export type Student = Schemas["StudentRead"];
export type StudentCreate = Schemas["StudentCreate"];
export type EnrollResult = Schemas["EnrollResult"];
export type Category = Schemas["CategoryRead"];
export type CategoryCreate = Schemas["CategoryCreate"];
export type CategoryUpdate = Schemas["CategoryUpdate"];
export type Assignment = Schemas["AssignmentRead"];
export type AssignmentCreate = Schemas["AssignmentCreate"];
export type AssignmentUpdate = Schemas["AssignmentUpdate"];
export type GradeStatus = Schemas["GradeStatus"];
export type GradeInput = Schemas["GradeInput"];
export type Grade = Schemas["GradeRead"];
export type Cell = Schemas["CellRead"];
export type Gradebook = Schemas["GradebookRead"];
export type GradebookRow = Schemas["GradebookRowRead"];
export type CategoryGrade = Schemas["CategoryGradeRead"];
export type StudentReport = Schemas["StudentReportRead"];
export type ReportCourse = Schemas["ReportCourseRead"];
export type ReportCategory = Schemas["ReportCategoryRead"];
export type ReportAssignment = Schemas["ReportAssignmentRead"];
export type AssignmentStats = Schemas["AssignmentStatsRead"];
export type RosterImportResult = Schemas["RosterImportResult"];
