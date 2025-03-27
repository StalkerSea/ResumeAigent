"""
This module contains the FacadeManager class, which is responsible for managing the interaction between the user and other components of the application.
"""
# app/libs/resume_and_cover_builder/manager_facade.py
import copy
from datetime import datetime
import json
import re
import inquirer
from pathlib import Path

from loguru import logger

from src.libs.resume_and_cover_builder.llm.llm_job_parser import LLMParser
from src.job.job import Job
from src.libs.resume_and_cover_builder.utils import Utils
from src.resume_builder.utils import HTML_to_PDF
from .config import global_config
from config import LLM_MODEL_TYPE, LLM_MODEL

class ResumeFacade:
    def __init__(self, api_key, style_manager, resume_generator, resume_object, output_path):
        """
        Initialize the FacadeManager with the given API key, style manager, resume generator, resume object, and log path.
        Args:
            api_key (str): The OpenAI API key to be used for generating text.
            style_manager (StyleManager): The StyleManager instance to manage the styles.
            resume_generator (ResumeGenerator): The ResumeGenerator instance to generate resumes and cover letters.
            resume_object (str): The resume object to be used for generating resumes and cover letters.
            output_path (str): The path to the log file.
        """
        lib_directory = Path(__file__).resolve().parent
        global_config.STRINGS_MODULE_RESUME_PATH = lib_directory / "resume_prompt/strings.py"
        global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH = lib_directory / "resume_job_description_prompt/strings.py"
        global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = lib_directory / "cover_letter_prompt/strings.py"
        global_config.STRINGS_MODULE_NAME = "strings"
        global_config.STYLES_DIRECTORY = lib_directory / "resume_style"
        global_config.LOG_OUTPUT_FILE_PATH = output_path
        global_config.API_KEY = api_key
        global_config.LLM_MODEL_TYPE = LLM_MODEL_TYPE
        global_config.LLM_MODEL = LLM_MODEL
        self.style_manager = style_manager
        self.resume_generator = resume_generator
        self.resume_generator.set_resume_object(resume_object)
        self.selected_style = None  # Property to store the selected style
        self.skills = set() # Property to store the user's skills
    
    def set_driver(self, driver):
         self.driver = driver

    def prompt_user(self, choices: list[str], message: str) -> str:
        """
        Prompt the user with the given message and choices.
        Args:
            choices (list[str]): The list of choices to present to the user.
            message (str): The message to display to the user.
        Returns:
            str: The choice selected by the user.
        """
        questions = [
            inquirer.List('selection', message=message, choices=choices),
        ]
        return inquirer.prompt(questions)['selection']

    def prompt_for_text(self, message: str) -> str:
        """
        Prompt the user to enter text with the given message.
        Args:
            message (str): The message to display to the user.
        Returns:
            str: The text entered by the user.
        """
        questions = [
            inquirer.Text('text', message=message),
        ]
        return inquirer.prompt(questions)['text']

    def link_to_job(self, job_url):
        self.driver.get(job_url)
        self.driver.implicitly_wait(3)
        
        body_element = Utils.get_job_info(self.driver)
        
        self.llm_job_parser = LLMParser(global_config)
        self.llm_job_parser.set_body_html(body_element)

        self.job = Job()
        job_details = self.llm_job_parser.extract_job_details()
        self.job.role = job_details["role"]
        self.job.company = job_details["company"]
        self.job.description = job_details["description"]
        self.job.requirements = job_details["requirements"]
        self.job.location = job_details["location"]
        logger.info(f"Extracting job details from URL: {job_url}")
        
    def create_resume_pdf(self) -> tuple[bytes, str]:
        """
        Create a resume PDF using the selected style and the given job description text.
        Args:
            job_url (str): The job URL to generate the hash for.
            job_description_text (str): The job description text to include in the resume.
        Returns:
            tuple: A tuple containing the PDF content as bytes and the unique filename.
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError("You must choose a style before generating the PDF.")
        
        html_resume = self.resume_generator.create_resume(style_path)
        result = HTML_to_PDF(html_resume, self.driver)
        self.driver.quit()
        return result

    def util_create_resume_from_description(self, job_description: str, job_title: str, company_name: str):
        """
        Generate a tailored resume for a job based on its description, title, and company name.
        
        Args:
            job_description: The full text of the job description
            job_title: The title of the job position
            company_name: The name of the company
            
        Returns:
            Tuple containing:
                - Base64 encoded PDF of the tailored resume
                - Suggested name for the resume file
        """
        try:
            logger.info(f"Creating tailored resume for {job_title} at {company_name}")
            
            # Create a suggested name for the output file
            suggested_name = f"{company_name}_{job_title}".replace(" ", "_")
            
            # Generate a tailored resume using the job details
            prompt = (
                f"I want to tailor my resume for the following job position:\n\n"
                f"Job Title: {job_title}\n"
                f"Company: {company_name}\n\n"
                f"Job Description:\n{job_description}\n\n"
                f"Please analyze the job description and suggest which skills, experiences, "
                f"and achievements from my resume I should emphasize. Also suggest any "
                f"modifications to make my resume more relevant for this specific position."
            )
            
            # Get LLM recommendations for tailoring
            recommendations = self._get_llm_recommendations(prompt)
            
            # Apply tailoring recommendations to the resume
            tailored_resume = self._apply_tailoring_recommendations(recommendations)
            
            style_path = self.style_manager.get_style_path()
            if style_path is None:
                raise ValueError("You must choose a style before generating the PDF.")
            
            # Create a temporary Job object to pass to create_resume_tailored
            temp_job = Job()
            temp_job.title = job_title
            temp_job.company = company_name
            temp_job.description = job_description
            
            # Use the existing create_resume_tailored method which already generates HTML
            html_content = self.resume_generator.create_resume_tailored(style_path, temp_job)
            
            pdf_base64 = HTML_to_PDF(html_content, self.driver)
            
            return pdf_base64, suggested_name
        except Exception as e:
            logger.exception(f"Error creating tailored resume from description: {e}")
            raise
        
    def _get_llm_recommendations(self, prompt: str) -> dict:
        """Get recommendations from LLM for tailoring the resume using the existing LLMParser."""
        try:
            # Create a properly formatted prompt for the LLM
            tailoring_prompt = f"""Analyze this job description and provide specific recommendations for tailoring a resume.
            
            {prompt}
            
            Provide your recommendations in the following JSON format:
            {{
                "highlights": [list of key qualifications or skills to emphasize],
                "skills": [specific technical skills to highlight or add],
                "experience": [aspects of work experience to emphasize],
                "education": [relevant educational background to emphasize],
                "projects": [types of projects to highlight],
                "summary": "brief guidance on how to adjust the professional summary"
            }}
            
            ONLY respond with the JSON. Do not include any other text.
            """
            
            # Use the LLMParser for making the query
            if not hasattr(self, 'llm_parser'):
                from src.libs.resume_and_cover_builder.llm.llm_job_parser import LLMParser
                # Create a minimal config with API key
                from types import SimpleNamespace
                config = SimpleNamespace()
                config.model_type = getattr(global_config, 'LLM_MODEL_TYPE', 'openai')
                config.model_name = getattr(global_config, 'LLM_MODEL', 'gpt-4-mini')
                config.API_KEY = self.api_key
                
                self.llm_parser = LLMParser(config)
                
                # Need to initialize the parser with some content for the vectorstore
                # This is needed because the error says "Vectorstore not initialized"
                self.llm_parser.set_body_html(prompt)
            
            # Make the query to the LLM - direct approach since vectorstore might not be initialized
            try:
                raw_response = self.llm_parser._extract_information(tailoring_prompt, "Resume tailoring")
            except Exception as inner_e:
                logger.warning(f"Failed to use LLM parser's extract_information: {inner_e}")
                # Return a minimal structure to avoid failures
                return {
                    "highlights": [],
                    "skills": [],
                    "experience": [],
                    "education": [],
                    "projects": [],
                    "summary": "Highlight your relevant technical skills and experience."
                }
            
            # Clean and parse the response
            clean_response = self.llm_parser.clean_llm_response(raw_response)
            
            try:
                # Parse the JSON response
                recommendations = json.loads(clean_response)
                return recommendations
            except json.JSONDecodeError:
                # If JSON parsing fails, create a structured format manually
                logger.warning("Failed to parse LLM response as JSON, creating manual structure")
                # Create a manual recommendations dictionary
                manual_recommendations = {
                    "highlights": [],
                    "skills": [],
                    "experience": [],
                    "education": [],
                    "projects": [],
                    "summary": "Highlight relevant qualifications and experience for this position."
                }
                return manual_recommendations
                
        except Exception as e:
            logger.error(f"Error getting LLM recommendations: {e}")
            # Return a minimal structure to avoid failures
            return {
                "highlights": [],
                "skills": [],
                "experience": [],
                "education": [],
                "projects": [],
                "summary": ""
            }
    
    def _extract_list_items(self, text: str) -> list:
        """Helper method to extract items from a comma-separated list in text"""
        # Clean up the text
        text = text.replace('"', '').replace("'", "")
        # Split by commas and clean each item
        items = [item.strip() for item in text.split(',') if item.strip()]
        return items
        
    def _apply_tailoring_recommendations(self, recommendations: dict) -> object:
        """Apply tailoring recommendations to the resume object."""
        try:
            # Try to get the resume object from the resume_generator
            if hasattr(self.resume_generator, 'get_resume_object'):
                resume_obj = self.resume_generator.get_resume_object()
            else:
                # If get_resume_object isn't available, try to access the resume_object attribute directly
                resume_obj = getattr(self.resume_generator, 'resume_object', None)
                
            if not resume_obj:
                # If still no resume object, use the one provided during initialization
                resume_obj = self.resume_object
                
            if not resume_obj:
                logger.error("Resume object not found in resume_generator")
                raise ValueError("No resume object available")
            
            # Clone the resume to avoid modifying the original
            tailored_resume = copy.deepcopy(resume_obj)
            
            # Process recommendations - simplified implementation
            # This would be expanded based on your resume structure
            try:
                # Example implementation - adapt to your resume structure
                if 'skills' in recommendations and hasattr(tailored_resume, 'skills'):
                    # Reorder skills based on relevance
                    highlighted_skills = recommendations.get('skills', [])
                    if highlighted_skills and isinstance(tailored_resume.skills, list):
                        # Move highlighted skills to the front
                        for skill in reversed(highlighted_skills):
                            if skill in tailored_resume.skills:
                                tailored_resume.skills.remove(skill)
                                tailored_resume.skills.insert(0, skill)
                
                # Similar handling for experiences, projects, etc.
                logger.info("Applied tailoring recommendations to resume")
            except Exception as e:
                logger.warning(f"Could not fully apply recommendations: {e}")
            
            return tailored_resume
        except Exception as e:
            logger.error(f"Error applying tailoring recommendations: {e}")
            # Return the original resume object if available
            return self.resume_object

    

    def util_create_cover_letter(self) -> tuple[bytes, str]:
        """
        Create a cover letter based on the given job description text and job URL.
        Args:
            job_url (str): The job URL to generate the hash for.
            job_description_text (str): The job description text to include in the cover letter.
        Returns:
            tuple: A tuple containing the PDF content as bytes and the unique filename.
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError("You must choose a style before generating the PDF.")
        
        
        cover_letter_html = self.resume_generator.create_cover_letter_job_description(style_path, self.job.description)

        # Generate a unique name using the job URL hash
        suggested_name = self.job.role + "/" + self.job.company
        # suggested_name += hashlib.md5(self.job.link.encode()).hexdigest()[:10]
        suggested_name += "/" + datetime.now().strftime('%Y-%m-%d')

        result = HTML_to_PDF(cover_letter_html, self.driver)
        self.driver.quit()
        return result, suggested_name