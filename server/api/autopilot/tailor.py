# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""AI-powered resume and cover letter tailoring."""

import os
import requests
from anthropic import Anthropic
from typing import Dict, Optional
from api.settings import settings


class TailorEngine:
    """Generate tailored resumes and cover letters using Claude."""

    def __init__(self, api_key: Optional[str] = None):
        self.groq_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
        self.groq_model = settings.GROQ_MODEL
        self.groq_url = settings.GROQ_BASE_URL.rstrip("/")
        self.api_key = api_key or settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
        self.client = Anthropic(api_key=self.api_key) if self.api_key else None

    def _generate(self, prompt: str, max_tokens: int) -> str:
        """Use Groq first with fallback, then local Ollama, then Anthropic, then template fallback."""
        if self.groq_key:
            import time
            for attempt in range(2):
                try:
                    response = requests.post(
                        f"{self.groq_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.groq_key}"},
                        json={
                            "model": self.groq_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": max_tokens,
                            "temperature": 0.3,
                        },
                        timeout=90,
                    )
                    if response.status_code == 429 and attempt == 0:
                        time.sleep(2)
                        continue
                    if response.ok:
                        content = response.json()["choices"][0]["message"]["content"].strip()
                        if content:
                            return content
                except Exception:
                    if attempt == 0:
                        time.sleep(1)

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "mistral", "prompt": prompt, "stream": False},
                timeout=120,
            )
            if response.ok:
                text = (response.json().get("response") or "").strip()
                if text:
                    return text
        except (requests.RequestException, KeyError):
            pass

        if self.client:
            try:
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                if response.content and response.content[0].text:
                    return response.content[0].text
            except Exception:
                pass

        # Fallback template if remote AI services are temporarily unavailable or rate limited
        return self._template_fallback(prompt)

    def _template_fallback(self, prompt: str) -> str:
        """Deterministic fallback when external AI APIs are rate limited."""
        return (
            "SUMMARY\nExperienced professional with strong background in software quality, "
            "automation, and systems integration.\n\nEXPERIENCE\nDemonstrated expertise in "
            "cross-functional collaboration, technical execution, and quality deliverables.\n\n"
            "SKILLS\nAutomation, Python, SQL, Testing, Integration, Data Quality."
        )

    def tailor_resume(self, job_title: str, company: str, job_description: str,
                     user_profile: Dict) -> str:
        """Generate a tailored resume for the specific job."""

        skills = ", ".join(user_profile.get("skills", []))
        experience = user_profile.get("experience", "")

        prompt = f"""You are an expert resume writer. Tailor this resume for the specific job.

JOB DETAILS:
Title: {job_title}
Company: {company}
Description: {job_description[:500]}

CANDIDATE PROFILE:
Skills: {skills}
Experience: {experience[:1000]}

INSTRUCTIONS:
1. Reorder skills to match the job requirements first
2. Highlight relevant experience from the job description
3. Add metrics and achievements that align with the role
4. Keep it to 1 page when formatted
5. Make it ATS-friendly with standard section headers
6. Focus on impact and results

OUTPUT ONLY THE RESUME TEXT, no other commentary."""

        return self._generate(prompt, 2000)

    def generate_cover_letter(self, job_title: str, company: str,
                             job_description: str, user_profile: Dict) -> str:
        """Generate a personalized cover letter."""

        name = user_profile.get("name", "Candidate")
        skills = ", ".join(user_profile.get("skills", [])[:5])

        prompt = f"""You are an expert cover letter writer. Write a compelling, personalized cover letter.

JOB:
Title: {job_title}
Company: {company}
Key Requirements: {job_description[:300]}

CANDIDATE:
Name: {name}
Top Skills: {skills}

INSTRUCTIONS:
1. Opening: Hook with enthusiasm for the specific role at the specific company
2. Body: Show 2-3 specific ways your skills match the role
3. Achievement: Include one concrete achievement with metrics
4. Closing: Call to action and genuine interest
5. Tone: Professional but warm, confident but not arrogant
6. Length: 3-4 paragraphs (250-350 words)
7. Personalization: Reference something specific from the job description

OUTPUT ONLY THE COVER LETTER, no subject line or salutations."""

        return self._generate(prompt, 1500)

    def extract_job_keywords(self, job_description: str) -> Dict:
        """Extract key skills and requirements from job description."""

        prompt = f"""Extract the top 5-10 most important skills/requirements from this job description.

JOB DESCRIPTION:
{job_description[:1000]}

Return ONLY a JSON object with:
- "skills": ["skill1", "skill2", ...]
- "experience_years": number
- "level": "entry|mid|senior"

Return only valid JSON, no other text."""

        # Parse the JSON response
        import json
        try:
            return json.loads(self._generate(prompt, 500))
        except:
            return {"skills": [], "experience_years": 0, "level": "mid"}
