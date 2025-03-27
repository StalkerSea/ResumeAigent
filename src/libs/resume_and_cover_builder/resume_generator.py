"""
This module is responsible for generating resumes and cover letters using the LLM model.
"""
# app/libs/resume_and_cover_builder/resume_generator.py
from string import Template
from typing import Any
from src.job.job import Job
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMResumer
from src.libs.resume_and_cover_builder.llm.llm_generate_resume_from_job import LLMResumeJobDescription
from src.libs.resume_and_cover_builder.llm.llm_generate_cover_letter_from_job import LLMCoverLetterJobDescription
from .module_loader import load_module
from .config import global_config

class ResumeGenerator:
    def __init__(self):
        pass
    
    def set_resume_object(self, resume_object):
        self.resume_object = resume_object

    def get_resume_object(self):
        return self.resume_object
         
    def _create_resume(self, gpt_answerer: Any, style_path: str, job: Job = None):
        gpt_answerer.set_resume(self.resume_object)
        
        # Read the HTML template
        template = Template(global_config.html_template)
        
        try:
            with open(style_path, "r") as f:
                style_css = f.read()  # Correction: call the `read` method with parentheses.
        except FileNotFoundError:
            raise ValueError(f"The style file was not found in the path: {style_path}")
        except Exception as e:
            raise RuntimeError(f"Error while reading CSS file: {e}")
        
        # Generate resume HTML
        body_html = gpt_answerer.generate_html_resume(job)
        
        # Apply content to the template
        return template.substitute(body=body_html, style_css=style_css)

    def create_resume(self, style_path):
        strings = load_module(global_config.STRINGS_MODULE_RESUME_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMResumer(global_config, strings)
        return self._create_resume(gpt_answerer, style_path)

    def create_resume_tailored(self, style_path: str, job: Job):
        strings = load_module(global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMResumeJobDescription(global_config, strings)
        gpt_answerer.set_job_description_from_text(job.description)
        return self._create_resume(gpt_answerer, style_path, job)

    def create_cover_letter_job_description(self, style_path: str, job_description_text: str):
        strings = load_module(global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMCoverLetterJobDescription(global_config, strings)
        gpt_answerer.set_resume(self.resume_object)
        gpt_answerer.set_job_description_from_text(job_description_text)
        cover_letter_html = gpt_answerer.generate_cover_letter()
        template = Template(global_config.html_template)
        with open(style_path, "r") as f:
            style_css = f.read()
        return template.substitute(body=cover_letter_html, style_css=style_css)

    def _create_resume_2(self, gpt_answerer: Any, style_path, temp_html_path):
        gpt_answerer.set_resume(self.resume_object)
        template = Template(global_config.html_template)
        message = template.substitute(markdown=gpt_answerer.generate_html_resume(), style_path=style_path)
        with open(temp_html_path, 'w', encoding='utf-8') as temp_file:
            temp_file.write(message)

    def create_resume_job_description_url(self, style_path: str, url_job_description: str, temp_html_path):
        strings = load_module(global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMResumeJobDescription(global_config.API_KEY, strings)
        gpt_answerer.set_job_description_from_url(url_job_description)
        self._create_resume_2(gpt_answerer, style_path, temp_html_path)

    def create_resume_job_description_text(self, style_path: str, job_description_text: str, temp_html_path):
        strings = load_module(global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH, global_config.STRINGS_MODULE_NAME)
        gpt_answerer = LLMResumeJobDescription(global_config.API_KEY, strings)
        gpt_answerer.set_job_description_from_text(job_description_text)
        self._create_resume_2(gpt_answerer, style_path, temp_html_path)
