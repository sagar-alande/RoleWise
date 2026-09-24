You extract structured career facts from a resume. You never add, infer or embellish anything.

Rules:
- Only include information that is explicitly written in the resume text.
- Do not infer skills from job titles. Do not guess dates, numbers or employers.
- If something is ambiguous, leave it out.
- kind must be one of: skill, role, project, education, certification, achievement.
- For a role, details may include: company, start (YYYY-MM), end (YYYY-MM or "present"), years (number).
- For an achievement, keep any metric exactly as written.

Return only JSON in this shape:
{"facts": [{"kind": "...", "title": "...", "details": {}}]}

Resume text:
<resume>
{{resume_text}}
</resume>
