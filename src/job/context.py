from src.job.job import Job
from src.job.application import JobApplication


from dataclasses import dataclass

@dataclass
class JobContext:
    job: Job = None
    job_application: JobApplication = None