-- Migration 008 (26 Nov 2026): signed-out visitors cannot call the size-grade helper.
revoke execute on function public.size_grade_for(numeric) from anon, public;
grant execute on function public.size_grade_for(numeric) to authenticated;
