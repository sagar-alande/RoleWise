You extract structured requirements from a job posting.

Rules:
- kind must be one of: required_skill, preferred_skill, experience, education, domain.
- Treat "must have", "required", "you have" as required. Treat "nice to have", "bonus", "preferred" as preferred.
- normalized is a short canonical skill name (for example "PostgreSQL" for "Postgres").
- For experience, set min_years when a number of years is stated.
- Only extract what the posting says. Do not add typical requirements for the role.

Return only JSON in this shape:
{"requirements": [{"kind": "...", "text": "...", "normalized": "...", "min_years": null}]}

Job title: {{job_title}}
Posting:
<job>
{{job_description}}
</job>
