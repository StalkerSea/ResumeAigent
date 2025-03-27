from dataclasses import dataclass
from typing import Optional, Literal
from src.app_logging import logger

@dataclass
class Job:
    """
    Represents a job posting with all its details and metadata.
    
    Attributes:
        Basic Information:
            id: Unique identifier for the job
            title: Job title/position
            company: Company name
            location: Job location
            link: URL to the job posting
            
        Job Details:
            work_type: Type of work arrangement (Remote/Hybrid/On-site)
            salary: Salary information if available
            description: Full job description
            summarize_job_description: Summarized version of the job description
            
        Application Status:
            viewed: Whether the job has been viewed
            posted_time: When the job was posted
            easy_apply: Whether the job supports Easy Apply
            apply_method: Method of application
            insights: Additional job insights
            
        Recruiter Information:
            recruiter_link: Link to recruiter's profile
            
        Application Documents:
            resume_path: Path to resume file
            cover_letter_path: Path to cover letter file
    """
    # Basic Information
    id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    link: str = ""
    
    # Job Details
    work_type: Optional[Literal['Remote', 'Hybrid', 'On-site']] = None
    salary: Optional[str] = None
    description: str = ""
    summarize_job_description: str = ""
    
    # Application Status
    viewed: bool = False
    posted_time: Optional[str] = None
    easy_apply: bool = False
    apply_method: str = ""
    insights: Optional[str] = None
    
    # Recruiter Information
    recruiter_link: str = ""
    
    # Application Documents (TODO: Move to JobApplication)
    resume_path: str = ""
    cover_letter_path: str = ""

    def set_summarize_job_description(self, summarize_job_description: str) -> None:
        """Sets the summarized version of the job description."""
        logger.debug(f"Setting summarized job description: {summarize_job_description}")
        self.summarize_job_description = summarize_job_description

    def set_job_description(self, description: str) -> None:
        """Sets the full job description."""
        logger.debug(f"Setting job description: {description}")
        self.description = description

    def set_recruiter_link(self, recruiter_link: str) -> None:
        """Sets the recruiter's profile link."""
        logger.debug(f"Setting recruiter link: {recruiter_link}")
        self.recruiter_link = recruiter_link

    def formatted_job_information(self) -> str:
        """
        Formats the job information as a markdown string.
        Returns:
            str: Formatted job information in markdown format
        """
        logger.debug(f"Formatting job information for job: {self.title} at {self.company}")
        job_information = f"""
        # Job Description
        ## Job Information 
        - Position: {self.title}
        - At: {self.company}
        - Location: {self.location} {f'({self.work_type})' if self.work_type else ''}
        - Salary: {self.salary or 'Not specified'}
        - Posted: {self.posted_time or 'Unknown'}
        - Easy Apply: {'Yes' if self.easy_apply else 'No'}
        - Recruiter Profile: {self.recruiter_link or 'Not available'}
        
        ## Description
        {self.description or 'No description provided.'}
        
        ## Additional Insights
        {self.insights or 'No additional insights available.'}
        """
        formatted_information = job_information.strip()
        logger.debug(f"Formatted job information: {formatted_information}")
        return formatted_information

    @property
    def is_complete(self) -> bool:
        """Check if all required fields are populated."""
        required_fields = ['id', 'title', 'company', 'location', 'link']
        return all(getattr(self, field) for field in required_fields)