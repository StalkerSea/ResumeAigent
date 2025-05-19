"""
This module is responsible for generating resumes and cover letters using the LLM model.
"""
# app/libs/resume_and_cover_builder/resume_generator.py
from string import Template
from typing import Any
from src.job import Job
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMResumer
from src.libs.resume_and_cover_builder.llm.llm_generate_resume_from_job import LLMResumeJobDescription
from src.libs.resume_and_cover_builder.llm.llm_generate_cover_letter_from_job import LLMCoverLetterJobDescription
from src.libs.resume_and_cover_builder.llm.prompt_builder.prompt_builder import PromptBuilder
from settings.config import global_config
from src.logging import logger

class ResumeGenerator:
    def __init__(self):
        self.prompt_builder = PromptBuilder()
    
    def set_resume_object(self, resume_object):
         self.resume_object = resume_object
         
    def _create_resume(self, gpt_answerer: Any, style_path: str, job: Job = None):
        gpt_answerer.set_resume(self.resume_object)
        
        # Read the HTML template
        template = Template(global_config.html_template)

         # Set prompts using localized strings
        if job:
            gpt_answerer.prompts = {
                'header': self.prompt_builder.get_header_prompt(self.resume_object.personal_information),
                'education': self.prompt_builder.get_education_prompt(self.resume_object.education, job.description),
                'experience': self.prompt_builder.get_experience_prompt(self.resume_object.experience, job.description),
                'projects': self.prompt_builder.get_projects_prompt(self.resume_object.projects, job.description),
                'achievements': self.prompt_builder.get_achievements_prompt(self.resume_object.achievements, job.description),
                'certifications': self.prompt_builder.get_certifications_prompt(self.resume_object.certifications, job.description),
                'skills': self.prompt_builder.get_skills_prompt(
                    self.resume_object.skills,
                    self.resume_object.languages,
                    self.resume_object.interests,
                    job.description
                )
            }
        else:
            gpt_answerer.prompts = {
                'header': self.prompt_builder.get_header_prompt(self.resume_object.personal_information),
                'education': self.prompt_builder.get_education_prompt(self.resume_object.education),
                'experience': self.prompt_builder.get_experience_prompt(self.resume_object.experience),
                'projects': self.prompt_builder.get_projects_prompt(self.resume_object.projects),
                'achievements': self.prompt_builder.get_achievements_prompt(self.resume_object.achievements),
                'certifications': self.prompt_builder.get_certifications_prompt(self.resume_object.certifications),
                'skills': self.prompt_builder.get_skills_prompt(
                    self.resume_object.skills,
                    self.resume_object.languages,
                    self.resume_object.interests
                )
            }
        
        try:
            with open(style_path, "r") as f:
                style_css = f.read()  # Correction: call the `read` method with parentheses.
        except FileNotFoundError:
            raise ValueError(f"The style file was not found in the path: {style_path}")
        except Exception as e:
            raise RuntimeError(f"Error while reading CSS file: {e}")
        
        # Generate resume HTML
        with LLMResumer(global_config) as resumer:
            resumer.set_resume(self.resume_object)
            try:
                html_content = resumer.generate_html_resume(job)
                # Apply content to the template
                return template.substitute(body=html_content, style_css=style_css)
            except Exception as e:
                logger.error(f"Failed to generate resume: {str(e)}")
                raise
        

    def create_resume(self, style_path: str) -> str:
        """Create a regular resume without job-specific tailoring."""
        gpt_answerer = LLMResumer(global_config)
        return self._create_resume(gpt_answerer, style_path)
    
    def create_resume_tailored(self, style_path: str, job: Job) -> str:
        """Create a resume tailored for a specific job."""
        gpt_answerer = LLMResumeJobDescription(global_config)
        gpt_answerer.set_job_description_from_text(job.description)
        return self._create_resume(gpt_answerer, style_path, job)
    
    def create_cover_letter_job_description(self, style_path: str, job_description_text: str) -> str:
        """Create a cover letter for a specific job description."""
        gpt_answerer = LLMCoverLetterJobDescription(global_config)
        gpt_answerer.set_resume(self.resume_object)
        gpt_answerer.set_job_description_from_text(job_description_text)
        
        # Generate cover letter using localized prompts
        cover_letter_html = gpt_answerer.generate_cover_letter()
        
        # Apply template
        template = Template(global_config.html_template)
        with open(style_path, "r") as f:
            style_css = f.read()
        return template.substitute(body=cover_letter_html, style_css=style_css)
    
    
    