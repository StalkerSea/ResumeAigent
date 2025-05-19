from typing import Dict, Any
from settings.localizations.manager import LocalizationManager

class PromptBuilder:
    def __init__(self):
        self.localization = LocalizationManager()
        
    def _build_requirements_list(self, requirements: list) -> str:
        """Convert requirements list to numbered string format"""
        return "\n".join(f"{i+1}. **{req}**" for i, req in enumerate(requirements))
        
    def build_prompt(self, section: str, context: Dict[str, Any], job_description: str = None) -> str:
        """
        Build a prompt using localized strings and provided context.
        
        Args:
            section: The section of the resume (e.g., "header", "education")
            context: Dictionary containing the information to insert
            job_description: Optional job description for tailored resumes
        """
        base_path = "prompts.resume."
        common = self.localization.get_string(f"{base_path}common")
        section_data = self.localization.get_string(f"{base_path}{section}")
        
        # Build the prompt without system role
        prompt = f"""{section_data['title']}
    
    {self._build_requirements_list(section_data['requirements'])}
    
    {common['improvement_note']}
    {common['omit_note']}
    
    - **My information:**  
      {context['data']}
    """
        
        # Add job description if provided
        if job_description:
            prompt += f"""
    - **Job Description:**  
      {job_description}
    """
        
        # Add the corresponding template
        template = globals().get(f"prompt_{section}_template", "")
        return prompt + template

    def get_header_prompt(self, personal_information: Dict) -> str:
        return self.build_prompt("header", {"data": personal_information})

    def get_education_prompt(self, education: Dict, job_description: str = None) -> str:
        return self.build_prompt("education", {"data": education}, job_description)

    def get_experience_prompt(self, experience: Dict, job_description: str = None) -> str:
        return self.build_prompt("experience", {"data": experience}, job_description)

    def get_projects_prompt(self, projects: Dict, job_description: str = None) -> str:
        return self.build_prompt("projects", {"data": projects}, job_description)

    def get_achievements_prompt(self, achievements: Dict, job_description: str = None) -> str:
        return self.build_prompt("achievements", {"data": achievements}, job_description)

    def get_certifications_prompt(self, certifications: Dict, job_description: str = None) -> str:
        return self.build_prompt("certifications", {"data": certifications}, job_description)

    def get_skills_prompt(self, skills: Dict, languages: Dict, interests: Dict, job_description: str = None) -> str:
        context = {
            "data": f"""Skills: {skills}
Languages: {languages}
Interests: {interests}"""
        }
        return self.build_prompt("skills", context, job_description)