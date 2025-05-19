from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Union
import yaml
from pydantic import BaseModel, EmailStr, HttpUrl, Field

class PersonalInformation(BaseModel):
    name: Optional[str]
    surname: Optional[str]
    date_of_birth: Optional[str]
    country: Optional[str]
    city: Optional[str]
    address: Optional[str]
    zip_code: Optional[str] = Field(None, min_length=5, max_length=10)
    phone_prefix: Optional[str]
    phone: Optional[str]
    email: Optional[EmailStr]
    github: Optional[HttpUrl] = None
    linkedin: Optional[HttpUrl] = None

    def get(self, field: str, default: str = "") -> str:
        """
        Get a field value with a default if not present.
        Handles composite fields like 'location' or 'full_name'.
        """
        if field == "location":
            return f"{self.city or ''}, {self.country or ''}".strip()
        elif field == "name":
            return f"{self.name or ''} {self.surname or ''}".strip()
        elif field == "phone":
            return f"{self.phone_prefix or ''}{self.phone or ''}".strip()
        elif field == "github":
            return str(self.github) if self.github else ""
        elif field == "linkedin":
            return str(self.linkedin) if self.linkedin else ""
        elif hasattr(self, field):
            return str(getattr(self, field) or default)
        return default


class EducationDetails(BaseModel):
    education_level: Optional[str]
    institution: Optional[str]
    location: Optional[str]
    field_of_study: Optional[str]
    final_evaluation_grade: Optional[str]
    start_year: Optional[str]
    end_year: Optional[int]

    def get(self, field: str, default: str = "") -> str:
        """Get a field value with a default if not present."""
        if field == "university":
            return str(self.institution or default)
        elif field == "field":
            return str(self.field_of_study or default)
        elif field == "grade":
            return str(self.final_evaluation_grade or default)
        elif field == "start_year":
            return str(self.start_year or default)
        elif field == "end_year":
            return str(self.end_year or default)
        elif hasattr(self, field):
            return str(getattr(self, field) or default)
        return default


class ExperienceDetails(BaseModel):
    position: Optional[str]
    company: Optional[str]
    employment_period: Optional[str]
    location: Optional[str]
    industry: Optional[str]
    key_responsibilities: Optional[List[Dict[str, str]]] = None
    skills_acquired: Optional[List[str]] = None

    def get(self, field: str, default: str = "") -> str:
        """Get a field value with a default if not present."""
        if field == "position":
            return str(self.position or default)
        elif field == "start_date":
            # Assuming employment_period is in format "MM-YYYY - MM-YYYY"
            return self.employment_period.split(" - ")[0] if self.employment_period else default
        elif field == "end_date":
            return self.employment_period.split(" - ")[1] if self.employment_period else default
        elif field == "responsibilities":
            # Changed from 'description' to 'responsibility' to match YAML structure
            return "\n".join(f"<li>{r['responsibility']}</li>" for r in (self.key_responsibilities or []))
        elif hasattr(self, field):
            return str(getattr(self, field) or default)
        return default


class Project(BaseModel):
    name: Optional[str]
    description: Optional[str]
    link: Optional[HttpUrl] = None

    def get(self, field: str, default: str = "") -> str:
        """Get a field value with a default if not present."""
        if field == "project_name":
            return str(self.name or default)
        elif field == "repo_url":
            return str(self.link) if self.link else default
        elif field == "achievements":
            return f"<li>{self.description}</li>" if self.description else default
        elif hasattr(self, field):
            return str(getattr(self, field) or default)
        return default


class Achievement(BaseModel):
    name: Optional[str]
    description: Optional[str]

    def get(self, field: str, default: str = "") -> str:
        """Get a field value with a default if not present."""
        if field == "award_name":
            return str(self.name or default)
        elif hasattr(self, field):
            return str(getattr(self, field) or default)
        return default

class Certifications(BaseModel):
    name: Optional[str]
    description: Optional[str]

    def get(self, field: str, default: str = "") -> str:
        """Get a field value with a default if not present."""
        if field == "cert_name":
            return str(self.name or default)
        elif hasattr(self, field):
            return str(getattr(self, field) or default)
        return default


class Language(BaseModel):
    language: Optional[str]
    proficiency: Optional[str]

    def get(self, field: str, default: str = "") -> str:
        """Get a field value with a default if not present."""
        if field == "full_description":
            return f"{self.language} - {self.proficiency}" if self.language and self.proficiency else default
        elif hasattr(self, field):
            return str(getattr(self, field) or default)
        return default


class Availability(BaseModel):
    notice_period: Optional[str]


class SalaryExpectations(BaseModel):
    salary_range_usd: Optional[str]


class SelfIdentification(BaseModel):
    gender: Optional[str]
    pronouns: Optional[str]
    veteran: Optional[str]
    disability: Optional[str]
    ethnicity: Optional[str]


class LegalAuthorization(BaseModel):
    eu_work_authorization: Optional[str]
    us_work_authorization: Optional[str]
    requires_us_visa: Optional[str]
    requires_us_sponsorship: Optional[str]
    requires_eu_visa: Optional[str]
    legally_allowed_to_work_in_eu: Optional[str]
    legally_allowed_to_work_in_us: Optional[str]
    requires_eu_sponsorship: Optional[str]


class Resume(BaseModel):
    personal_information: Optional[PersonalInformation]
    education: Optional[List[EducationDetails]] = None
    experience: Optional[List[ExperienceDetails]] = None
    projects: Optional[List[Project]] = None
    achievements: Optional[List[Achievement]] = None
    certifications: Optional[List[Certifications]] = None
    languages: Optional[List[Language]] = None
    interests: Optional[List[str]] = None
    skills: set[str] = Field(default_factory=set)

    def __init__(self, yaml_str: str):
        try:
            # Parse the YAML string
            data = yaml.safe_load(yaml_str)

            # Create an instance of Resume from the parsed data
            super().__init__(**data)
        except yaml.YAMLError as e:
            raise ValueError("Error parsing YAML file.") from e
        except Exception as e:
            raise Exception(f"Unexpected error while parsing YAML: {e}") from e


    def _process_personal_information(self, data: Dict[str, Any]) -> PersonalInformation:
        try:
            return PersonalInformation(**data)
        except TypeError as e:
            raise TypeError(f"Invalid data for PersonalInformation: {e}") from e
        except AttributeError as e:
            raise AttributeError(f"AttributeError in PersonalInformation: {e}") from e
        except Exception as e:
            raise Exception(f"Unexpected error in PersonalInformation processing: {e}") from e

    def _process_education(self, data: List[Dict[str, Any]]) -> List[EducationDetails]:
        education_list = []
        for edu in data:
            try:
                education = EducationDetails(
                    education_level=edu.get('education_level'),
                    institution=edu.get('institution'),
                    location=edu.get('location'),
                    field_of_study=edu.get('field_of_study'),
                    final_evaluation_grade=edu.get('final_evaluation_grade'),
                    start_year=edu.get('start_year'),
                    end_year=edu.get('end_year'),
                )
                education_list.append(education)
            except KeyError as e:
                raise KeyError(f"Missing field in education details: {e}") from e
            except TypeError as e:
                raise TypeError(f"Invalid data for Education: {e}") from e
            except AttributeError as e:
                raise AttributeError(f"AttributeError in Education: {e}") from e
            except Exception as e:
                raise Exception(f"Unexpected error in Education processing: {e}") from e
        return education_list

    def _process_experience(self, data: List[Dict[str, Any]]) -> List[ExperienceDetails]:
        experience_list = []
        for exp in data:
            try:
                key_responsibilities = [
                    Responsibility(description=list(resp.values())[0])
                    for resp in exp.get('key_responsibilities', [])
                ]
                skills_acquired = [str(skill) for skill in exp.get('skills_acquired', [])]
                experience = ExperienceDetails(
                    position=exp['position'],
                    company=exp['company'],
                    employment_period=exp['employment_period'],
                    location=exp['location'],
                    industry=exp['industry'],
                    key_responsibilities=key_responsibilities,
                    skills_acquired=skills_acquired
                )
                experience_list.append(experience)
            except KeyError as e:
                raise KeyError(f"Missing field in experience details: {e}") from e
            except TypeError as e:
                raise TypeError(f"Invalid data for Experience: {e}") from e
            except AttributeError as e:
                raise AttributeError(f"AttributeError in Experience: {e}") from e
            except Exception as e:
                raise Exception(f"Unexpected error in Experience processing: {e}") from e
        return experience_list

@dataclass
class Responsibility:
    description: str