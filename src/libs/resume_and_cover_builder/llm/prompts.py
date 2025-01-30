class Prompts:
    system_context = """You are a professional resume writer and career advisor. 
    Analyze the provided information and format it appropriately for a resume or application."""

    personal_information_template = """
    Based on the provided information, extract or generate appropriate personal details:
    - Full Name
    - Email Address
    - Phone Number
    - Location (City, State/Province, Country)
    - Professional Title
    - LinkedIn Profile (if available)
    
    Context: {context}
    """

    self_identification_template = """
    Extract or generate appropriate self-identification information if provided:
    - Gender (if disclosed)
    - Ethnicity (if disclosed)
    - Veteran Status (if applicable)
    - Disability Status (if disclosed)
    
    Context: {context}
    """

    legal_authorization_template = """
    Determine work authorization status:
    - Citizenship Status
    - Work Visa Requirements
    - Right to Work Documentation
    - Need for Sponsorship
    
    Context: {context}
    """

    work_preferences_template = """
    Extract work preferences and requirements:
    - Desired Role Types
    - Preferred Industries
    - Work Environment (Remote/Hybrid/On-site)
    - Travel Willingness
    - Schedule Preferences
    
    Context: {context}
    """

    education_details_template = """
    Format education history:
    - Degree/Certification Name
    - Institution Name
    - Location
    - Graduation Date
    - GPA (if relevant)
    - Key Achievements
    - Relevant Coursework
    
    Context: {context}
    """

    experience_details_template = """
    Format work experience with:
    - Company Name
    - Position Title
    - Duration (MM/YYYY - MM/YYYY)
    - Location
    - Key Responsibilities
    - Achievements with measurable results
    - Technologies/Tools Used
    
    Context: {context}
    """

    projects_template = """
    Detail relevant projects:
    - Project Name
    - Duration
    - Technologies Used
    - Your Role
    - Project Description
    - Key Outcomes
    - Links (if available)
    
    Context: {context}
    """

    availability_template = """
    Specify availability:
    - Start Date
    - Notice Period
    - Preferred Working Hours
    - Time Zone
    
    Context: {context}
    """

    salary_expectations_template = """
    Provide salary requirements:
    - Expected Salary Range
    - Current Compensation (if applicable)
    - Benefit Requirements
    - Bonus Expectations
    
    Context: {context}
    """

    certifications_template = """
    List relevant certifications:
    - Certification Name
    - Issuing Organization
    - Date Obtained
    - Expiration Date (if applicable)
    - Certification ID
    
    Context: {context}
    """

    languages_template = """
    List language proficiencies:
    - Language Name
    - Proficiency Level (Basic/Intermediate/Advanced/Native)
    - Certifications (if any)
    
    Context: {context}
    """

    interests_template = """
    List relevant professional interests:
    - Technical Interests
    - Industry Interests
    - Professional Development Goals
    
    Context: {context}
    """

    coverletter_template = """
    Generate a professional cover letter including:
    - Company Name
    - Job Title
    - Key Qualifications
    - Relevant Experience
    - Why you're interested
    - How you can contribute
    
    Company Info: {company_info}
    Job Description: {job_description}
    Context: {context}
    """