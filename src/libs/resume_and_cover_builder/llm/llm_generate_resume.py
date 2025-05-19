"""
Create a class that generates a resume based on a resume and a resume template.
"""
# app/libs/resume_and_cover_builder/gpt_resume.py
import os
import textwrap
from settings.localizations.manager import LocalizationManager
from src.job import Job
from src.utils.utils import LoggerChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import traceback

# Load environment variables from .env file
load_dotenv()

# Configure log file
log_folder = 'log/resume/gpt_resume'
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(log_path / "gpt_resume.log", rotation="1 day", compression="zip", retention="7 days", level="DEBUG")

# Update logger configuration
logger.configure(
    handlers=[
        {
            "sink": log_path / "gpt_resume.log",
            "rotation": "1 day",
            "compression": "zip",
            "retention": "7 days",
            "level": "DEBUG",
            "enqueue": True,  # Enable thread-safe logging
            "backtrace": True,
            "diagnose": True,
        }
    ]
)


class LLMModelFactory:
    @staticmethod
    def create_llm(model_type: str, model_name: str, api_key: str = None, **kwargs):
        model_type = model_type.lower()
        
        if model_type == "openai":
            return ChatOpenAI(
                model_name=model_name,
                openai_api_key=api_key,
                temperature=kwargs.get('temperature', 0.4)
            )
        elif model_type == "gemini":
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=kwargs.get('temperature', 0.4)
            )
        elif model_type == "ollama":
            return ChatOllama(
                model=model_name,
                temperature=kwargs.get('temperature', 0.4)
            )
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

class LLMResumer:
    def __init__(self, config):
        # Initialize LLM
        model_type = getattr(config, 'LLM_MODEL_TYPE', 'openai')
        model_name = getattr(config, 'LLM_MODEL', 'gpt-4-mini')
        api_key = config.API_KEY
        
        llm = LLMModelFactory.create_llm(
            model_type=model_type,
            model_name=model_name,
            api_key=api_key,
            temperature=0.4
        )
        self.llm_cheap = LoggerChatModel(llm)
        
        # Initialize localization manager
        self.localization = LocalizationManager()

        self._executor = None
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
        
        if hasattr(self, 'llm_cheap'):
            # Clean up any LLM resources if needed
            pass

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        """
        Preprocess the template string by removing leading whitespace and indentation.
        Args:
            template (str): The template string to preprocess.
        Returns:
            str: The preprocessed template string.
        """
        return textwrap.dedent(template)

    def _get_prompt_template(self, section: str, with_job: bool = False) -> str:
        """
        Get the prompt template from localization system and format it properly.
        
        Args:
            section (str): The section name (e.g., 'header', 'education')
            with_job (bool): Whether to include job-specific context
            
        Returns:
            str: The formatted prompt template
        """
        try:
            # Define input field mapping for each section
            input_field_mapping = {
                "header": "personal_information",
                "education": "education",
                "experience": "experience",
                "projects": "projects",
                "achievements": "achievements",
                "certifications": "certifications",
                "additional_skills": "skills",
                "relevant_skills": "skills"
            }
    
            base_path = "prompts.resume."
            template_path = f"templates.html.resume.{section}"

            section_2 = "skills" if section in ["additional_skills", "relevant_skills"] else section

            # Get prompt data
            prompt_data = self.localization.get_string(f"{base_path}{section_2}")

            # Get HTML template
            html_template = self.localization.get_string(template_path)
        
            logger.debug(f"Retrieved prompt data: {prompt_data}")
            
            # Check if prompt_data is a dictionary with the expected structure
            if not isinstance(prompt_data, dict) or 'title' not in prompt_data or 'requirements' not in prompt_data:
                logger.error(f"Invalid prompt data format for section {section}: {prompt_data}")
                raise ValueError(f"Invalid prompt data format for section {section}")
            
            # Get the correct input field name for this section
            input_field = input_field_mapping.get(section, "data")
            
            # Format the prompt from the localization data
            formatted_template = f"""{prompt_data['title']}
    
    Requirements:
    {chr(10).join(f'- {req}' for req in prompt_data['requirements'])}
    
    {self.localization.get_string('prompts.resume.common.improvement_note')}
    {self.localization.get_string('prompts.resume.common.omit_note')}
    
    Input Information:
    {{{input_field}}}
    
    Generate HTML using this structure:
    {html_template['structure'] if isinstance(html_template, dict) and 'structure' in html_template else html_template}
    """
            
            # Add base template suffix if it exists
            template_suffix = globals().get(f"prompt_{section}_template", "")
            if template_suffix:
                formatted_template += f"\n{template_suffix}"
            
            logger.debug(f"Final formatted template: {formatted_template}")
            return formatted_template
            
        except Exception as e:
            logger.error(f"Error formatting template for section {section}: {str(e)}")
            logger.debug(traceback.format_exc())
            raise ValueError(f"Failed to format template for section {section}: {str(e)}")

    def set_resume(self, resume) -> None:
        """
        Set the resume object to be used for generating the resume.
        Args:
            resume (Resume): The resume object to be used.
        """
        self.resume = resume

    def generate_header(self, data = None) -> str:
        """
        Generate the header section of the resume.
        Args:
            data (dict): The personal information to use for generating the header.
        Returns:
            str: The generated header section.
        """
        logger.debug("Starting header generation")
    
        header_prompt_template = self._preprocess_template_string(
            self._get_prompt_template("header")
        )
        
        prompt = ChatPromptTemplate.from_template(header_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        
        if data is None:
            personal_info = self.resume.personal_information
            input_data = {
                "name": personal_info.get("name"),
                "location": personal_info.get("location"),
                "phone": personal_info.get("phone"),
                "email": personal_info.get("email"),
                "linkedin": personal_info.get("linkedin"),
                "github": personal_info.get("github"),
                "personal_information": personal_info
            }
        else:
            input_data = data
        
        output = chain.invoke(input_data)
        logger.debug("Header generation completed")
        return output
    
    def generate_education_section(self, data = None) -> str:
        """
        Generate the education section of the resume.
        Args:
            data (dict): The education details to use for generating the education section.
        Returns:
            str: The generated education section.
        """
        logger.debug("Starting education section generation")

        template = self._get_prompt_template("education")
        education_prompt_template = self._preprocess_template_string(template)

        prompt = ChatPromptTemplate.from_template(education_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        
        if data is None:
            # Extract and format education details
            if not self.resume.education:
                return ""
                
            formatted_entries = []
            for edu in self.resume.education:
                formatted_entries.append({
                    "university": edu.get("university"),
                    "location": edu.get("location"),
                    "degree": edu.get("education_level"),
                    "field": edu.get("field"),
                    "grade": edu.get("grade"),
                    "start_year": edu.get("start_year"),
                    "end_year": edu.get("end_year")
                })
            
            input_data = {
                "education": self.resume.education,  # Full data for LLM context
                # Template variables
                "university": formatted_entries[0]["university"],
                "location": formatted_entries[0]["location"],
                "degree": formatted_entries[0]["degree"],
                "field": formatted_entries[0]["field"],
                "grade": formatted_entries[0]["grade"],
                "start_year": formatted_entries[0]["start_year"],
                "end_year": formatted_entries[0]["end_year"]
            }
        else:
            input_data = data
        
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")
        logger.debug("Education section generation completed")
        return output

    def generate_work_experience_section(self, data = None) -> str:
        """
        Generate the work experience section of the resume.
        Args:
            data (dict): The work experience details to use for generating the work experience section.
        Returns:
            str: The generated work experience section.
        """
        logger.debug("Starting work experience section generation")

        template = self._get_prompt_template("experience")
        work_experience_prompt_template = self._preprocess_template_string(template)

        prompt = ChatPromptTemplate.from_template(work_experience_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        
        if data is None:
            if not self.resume.experience:
                return ""
                
            # Extract and format experience details
            exp = self.resume.experience[0]  # Use first experience as template
            input_data = {
                "experience": self.resume.experience,  # Full data for LLM context
                # Template variables
                "company": exp.get("company"),
                "location": exp.get("location"),
                "position": exp.get("position"),
                "start_date": exp.get("start_date"),
                "end_date": exp.get("end_date"),
                "responsibilities": exp.get("responsibilities")
            }
        else:
            input_data = data
        
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")
        logger.debug("Work experience section generation completed")
        return output

    def generate_projects_section(self, data = None) -> str:
        """Generate the side projects section of the resume."""
        logger.debug("Starting side projects section generation")
    
        template = self._get_prompt_template("projects")
        projects_prompt_template = self._preprocess_template_string(template)
        prompt = ChatPromptTemplate.from_template(projects_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        
        if data is None:
            if not self.resume.projects:
                return ""
                
            # Extract and format project details
            project = self.resume.projects[0]  # Use first project as template
            input_data = {
                "projects": self.resume.projects,  # Full data for LLM context
                # Template variables
                "project_name": project.get("project_name"),
                "repo_url": project.get("repo_url"),
                "achievements": project.get("achievements")
            }
        else:
            input_data = data
        
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")
        return output
    
    def generate_achievements_section(self, data = None) -> str:
        """Generate the achievements section of the resume."""
        logger.debug("Starting achievements section generation")
    
        template = self._get_prompt_template("achievements")
        achievements_prompt_template = self._preprocess_template_string(template)
        prompt = ChatPromptTemplate.from_template(achievements_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        
        if data is None:
            if not self.resume.achievements:
                return ""
                
            # Extract and format achievement details
            achievement = self.resume.achievements[0]  # Use first achievement as template
            input_data = {
                "achievements": self.resume.achievements,  # Full data for LLM context
                # Template variables
                "award_name": achievement.get("award_name"),
                "description": achievement.get("description")
            }
        else:
            input_data = data
        
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")
        return output
    
    def generate_certifications_section(self, data = None) -> str:
        """Generate the certifications section of the resume."""
        logger.debug("Starting Certifications section generation")
    
        template = self._get_prompt_template("certifications")
        certifications_prompt_template = self._preprocess_template_string(template)
        prompt = ChatPromptTemplate.from_template(certifications_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        
        if data is None:
            if not self.resume.certifications:
                return ""
                
            # Extract and format certification details
            cert = self.resume.certifications[0]  # Use first certification as template
            input_data = {
                "certifications": self.resume.certifications,  # Full data for LLM context
                # Template variables
                "cert_name": cert.get("cert_name"),
                "description": cert.get("description")
            }
        else:
            input_data = data
        
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")
        return output
    
    def generate_additional_skills_section(self, data = None) -> str:
        """Generate the additional skills section of the resume."""
        logger.debug("Starting additional skills section generation")
        
        template = self._get_prompt_template("additional_skills") if data is None else self._get_prompt_template("relevant_skills")
        additional_skills_prompt_template = self._preprocess_template_string(template)
        prompt = ChatPromptTemplate.from_template(additional_skills_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
    
        if data is not None:
            languages = ', '.join([f"{lang.language} - {lang.proficiency}".strip() for lang in data['languages']]) if data['languages'] else ''
            input_data = {
                "languages": languages,
                "technical_skills": self.resume.skills,
                "domain_skills": data.get('job_requirements', ''),
                "other_skills": data.get('interests', '')
            }
        else:
            # Format languages string from Language objects
            languages = ', '.join([lang.get("full_description") for lang in (self.resume.languages or [])])
            input_data = {
                "languages": languages,
                "technical_skills": self.resume.skills,
                "other_skills": ', '.join(self.resume.interests) if self.resume.interests else ''
            }
        
        output = chain.invoke(input_data)
        logger.debug(f"Chain invocation result: {output}")
        return output

    def generate_html_resume(self, job: Job = None) -> str:
        """
        Generate the full HTML resume based on the resume object.
        Returns:
            str: The generated HTML resume.
        """
        if not self.resume:
            logger.error("The resume object is not set")
            raise ValueError("The resume object is not set.")

        # Define the section generation functions
        section_functions = {
            "header": lambda: self.generate_header() if self.resume.personal_information else "",
            "education": lambda: self.generate_education_section() if self.resume.education else "",
            "work_experience": lambda: self.generate_work_experience_section() if self.resume.experience else "",
            "projects": lambda: self.generate_projects_section() if self.resume.projects else "",
            "achievements": lambda: self.generate_achievements_section() if self.resume.achievements else "",
            "certifications": lambda: self.generate_certifications_section() if self.resume.certifications else "",
            "additional_skills": lambda: self._generate_skills_section(job) if any([
                self.resume.experience, self.resume.education,
                self.resume.languages, self.resume.interests, self.resume.skills
            ]) else ""
        }

        results = {}
        TIMEOUT_PER_SECTION = 30  # 30 seconds timeout per section

        # Use ThreadPoolExecutor with proper exception handling
        with ThreadPoolExecutor(max_workers=3) as executor:  # Limit concurrent workers
            future_to_section = {
                executor.submit(fn): section_name 
                for section_name, fn in section_functions.items()
            }
            
            # Wait for all futures to complete with timeout
            try:
                for future in as_completed(future_to_section.keys(), timeout=TIMEOUT_PER_SECTION):
                    section_name = future_to_section[future]
                    try:
                        result = future.result(timeout=TIMEOUT_PER_SECTION)
                        if result:
                            results[section_name] = result
                            logger.debug(f"Successfully generated {section_name} section")
                    except TimeoutError:
                        logger.error(f"Timeout generating {section_name} section")
                        future.cancel()
                    except Exception as e:
                        logger.error(f"Error generating {section_name} section: {str(e)}")
                        logger.debug(traceback.format_exc())
            except TimeoutError:
                logger.error("Overall timeout reached while generating resume sections")
            finally:
                # Cancel any remaining futures
                for future in future_to_section:
                    if not future.done():
                        future.cancel()

        # Helper method to safely get section content
        def get_section(name: str) -> str:
            return results.get(name, "")

        # Construct the final HTML
        full_resume = (
            "<body>\n"
            f"  {get_section('header')}\n"
            "  <main>\n"
            f"    {get_section('education')}\n"
            f"    {get_section('work_experience')}\n"
            f"    {get_section('projects')}\n"
            f"    {get_section('achievements')}\n"
            f"    {get_section('certifications')}\n"
            f"    {get_section('additional_skills')}\n"
            "  </main>\n"
            "</body>"
        )

        # Clean up HTML markers
        full_resume = full_resume.replace("```html", "").replace("```", "")
        return full_resume

    def _generate_skills_section(self, job: Job = None) -> str:
        """Helper method to generate skills section with proper input handling"""
        try:
            if job is not None and isinstance(job, Job):
                input_data = {
                    "interests": self.resume.interests,
                    "job_requirements": job.requirements,
                    "languages": self.resume.languages,
                }
                return self.generate_additional_skills_section(input_data)
            else:
                return self.generate_additional_skills_section()
        except Exception as e:
            logger.error(f"Error generating skills section: {str(e)}")
            return ""