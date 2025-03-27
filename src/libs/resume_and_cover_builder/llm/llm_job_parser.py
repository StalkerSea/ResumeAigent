import json
import os
import tempfile
import textwrap
import re
from typing import Dict, Optional  # For email validation
import numpy as np
from src.libs.resume_and_cover_builder.llm.llm_generate_resume import LLMModelFactory
from src.libs.resume_and_cover_builder.utils import LoggerChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from loguru import logger
from pathlib import Path
from langchain_text_splitters import TokenTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
# from requests.exceptions import HTTPError as HTTPStatusError  # HTTP error handling

# Embeddings
from langchain_ollama import OllamaEmbeddings
from langchain_community.embeddings import OpenAIEmbeddings, HuggingFaceEmbeddings

# Load environment variables from the .env file
load_dotenv()

# Configure the log file
log_folder = 'log/resume/gpt_resume'
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(log_path / "gpt_resume.log", rotation="1 day", compression="zip", retention="7 days", level="DEBUG")


class LLMParser:
    def __init__(self, config):
        model_type = getattr(config, 'LLM_MODEL_TYPE', 'openai')
        model_name = getattr(config, 'LLM_MODEL', 'gpt-4-mini')
        api_key = config.API_KEY
        # temp_model_name = 'nomic-embed-text:latest' if model_name == 'ollama' else model_name
        
        self.llm = LLMModelFactory.create_llm(
            model_type=model_type,
            model_name=model_name,
            api_key=api_key,
            temperature=0.4
        )
        self.llm_cheap = LoggerChatModel(self.llm)

        # Initialize embeddings based on model type
        if model_type == 'openai':
            self.llm_embeddings = OpenAIEmbeddings(openai_api_key=api_key)
        elif model_type == 'huggingface':
            self.llm_embeddings = HuggingFaceEmbeddings(model_name=model_name)
        elif model_type == 'ollama' or model_type == 'gemini':
            self.llm_embeddings = OllamaEmbeddings(model='nomic-embed-text:latest')
        else:
            raise ValueError(f"Unsupported model type for embeddings: {model_type}")

        self.vectorstore = None  # Will be initialized after document loading

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        """
        Preprocess the template string by removing leading whitespaces and indentation.
        Args:
            template (str): The template string to preprocess.
        Returns:
            str: The preprocessed template string.
        """
        return textwrap.dedent(template)
    
    def set_body_html(self, body_html):
        """
        Retrieves the job description from HTML, processes it, and initializes the vectorstore.
        Args:
            body_html (str): The HTML content to process.
        """

        # Save the HTML content to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as temp_file:
            temp_file.write(body_html)
            temp_file_path = temp_file.name 
        try:
            loader = TextLoader(temp_file_path, encoding="utf-8", autodetect_encoding=True)
            document = loader.load()
            logger.debug("Document successfully loaded.")
        except Exception as e:
            logger.error(f"Error during document loading: {e}")
            raise
        finally:
            os.remove(temp_file_path)
            logger.debug(f"Temporary file removed: {temp_file_path}")
        
        # Split the text into chunks
        text_splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=50)
        all_splits = text_splitter.split_documents(document)
        logger.debug(f"Text split into {len(all_splits)} fragments.")
        
        # Create the vectorstore using FAISS
        try:
            if isinstance(self.llm_embeddings, (OpenAIEmbeddings, HuggingFaceEmbeddings, OllamaEmbeddings)):
                # Standard approach for OpenAI and HuggingFace
                self.vectorstore = FAISS.from_documents(documents=all_splits, embedding=self.llm_embeddings)
            else:
                # Custom approach for Gemini
                # Convert documents to embeddings manually
                texts = [doc.page_content for doc in all_splits]
                embeddings = [self.llm_embeddings(text) for text in texts]
                
                # Create FAISS index directly
                dimension = len(embeddings[0])
                index = FAISS.IndexFlatL2(dimension)
                index.add(np.array(embeddings).astype('float32'))
                
                # Store the index and texts
                self.vectorstore = {
                    'index': index,
                    'texts': texts
                }
            logger.debug("Vectorstore successfully initialized.")
        except Exception as e:
            logger.error(f"Error during vectorstore creation: {e}")
            raise

    def _retrieve_context(self, query: str, top_k: int = 3) -> str:
        """
        Retrieves the most relevant text fragments using the retriever.
        Args:
            query (str): The search query.
            top_k (int): Number of fragments to retrieve.
        Returns:
            str: Concatenated text fragments.
        """
        if not self.vectorstore:
            raise ValueError("Vectorstore not initialized. Run extract_job_description first.")
        
        retriever = self.vectorstore.as_retriever()
        retrieved_docs = retriever.invoke(query)[:top_k]
        context = " ".join(doc.page_content for doc in retrieved_docs)
        logger.debug(f"Context retrieved for query '{query}': {context[:200]}...")  # Log the first 200 characters
        return context
    
    def _extract_information(self, question: str, retrieval_query: str) -> str:
        """
        Generic method to extract specific information using the retriever and LLM.
        Args:
            question (str): The question to ask the LLM for extraction.
            retrieval_query (str): The query to use for retrieving relevant context.
        Returns:
            str: The extracted information.
        """
        # First get the context
        raw_context = self._retrieve_context(retrieval_query)
        # Keep content of first major tag (body, main, div) even if unclosed
        context = re.sub(r'<(?!(?:body|main|div))[^>]*>(?:(?!</[^>]*>).)*$', '', raw_context)
        # Now safely remove all remaining HTML tags while preserving their content
        context = re.sub(r'<[^>]*>|</[^>]*>', '', context)
        
        prompt = ChatPromptTemplate.from_template(
            template="""
            You are an expert in extracting specific information from job descriptions. 
            Carefully read the job description context below and provide a clear and concise answer to the question.

            Context: {context}

            Question: {question}
            Answer:
            """
        )
        
        formatted_prompt = prompt.format(context=context, question=question)
        logger.debug(f"Formatted prompt for extraction: {formatted_prompt[:350]}...")  # Log the first 350 characters
        
        try:
            chain = prompt | self.llm | StrOutputParser()
            result = chain.invoke({"context": context, "question": question})
            # Remove code block markers and language tags
            logger.debug(f"Extracted information: {result}")
            return result
        except Exception as e:  
            logger.error(f"Error during information extraction: {e}")
            return ""
        
    def clean_llm_response(self, text: str) -> str:
        """Remove markdown code blocks and language tags from LLM response."""
        # Remove code block markers and language tags
        text = re.sub(r'```(?:json|html)?\n?', '', text)
        text = text.replace('```', '').replace('\n', '')
        # Trim whitespace
        return text.strip()
    
    def remove_html_tags(self, text: str) -> str:
        """
        Remove all HTML tags from input text while preserving content.
        
        Args:
            text (str): Input text containing HTML tags
            
        Returns:
            str: Clean text with HTML tags removed
        """
        # Remove all HTML tags using regex
        clean_text = re.sub(r'<[^>]+>', '', text)
        return clean_text.strip()
    
    def extract_job_details(self) -> Dict[str, Optional[str]]:
        """Extracts all job details in a single query."""
        
        unified_prompt = """Analyze the entire job posting. Extract ALL information. Format as JSON. Reply ONLY with the JSON:
        {
            "role": "exact job title as posted",
            "company": "company name",
            "description": "DETAILED description including: 1) What the role does 2) Day-to-day responsibilities 3) Team structure 4) Project scope 5) Key deliverables. Include ALL bullet points and paragraphs about responsibilities.",
            "requirements": "COMPLETE list as a string of: 1) Required technical skills 2) Years of experience 3) Education requirements 4) Certifications 5) Soft skills 6) Tools/technologies. Include ALL bullet points about requirements in the same string, if some aren't found, skip them. DO NOT mention 'Responsibilities' or 'Requirements' in the string.",
            "location": "job location, if Remote is mentioned anywhere use Remote, null if not specified"
        }
        
        IMPORTANT: Include ALL text from requirements and responsibilities sections. Do not summarize or add extra objects, the structure should remain unchanged. If any details are missing, ignore them."""
        
        retrieval_query = "Job posting details"
        
        try:
            # raw_response = self._extract_information(unified_prompt, retrieval_query)
            raw_response = self._extract_information(unified_prompt, retrieval_query)
            clean_response = self.clean_llm_response(raw_response)
            cleaner_response = self.remove_html_tags(clean_response)
            cleanest_response = cleaner_response.replace('\n', ' ').replace('\\n', ' ').replace('\r', '')
            return json.loads(cleanest_response)
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM response as JSON")
        return {
            "role": "",
            "company_name": "",
            "job_description": "",
            "location": None,
        }
    
    def extract_job_description(self) -> str:
        """
        Extracts the company name from the job description.
        Returns:
            str: The extracted job description.
        """
        question = "What is the job description of the company? Reply only with the job description, if not found, infer it, but avoid adding extra details; go straight to the point."
        retrieval_query = "Job description"
        logger.debug("Starting job description extraction.")
        return self._extract_information(question, retrieval_query)
    
    def extract_company_name(self) -> str:
        """
        Extracts the company name from the job description.
        Returns:
            str: The extracted company name.
        """
        question = "What is the company's name? Reply only with the company's name, if not found, infer it, but avoid adding extra details; go straight to the point."
        retrieval_query = "Company name"
        logger.debug("Starting company name extraction.")
        return self._extract_information(question, retrieval_query)
    
    def extract_role(self) -> str:
        """
        Extracts the sought role/title from the job description.
        Returns:
            str: The extracted role/title.
        """
        question = "What is the role or title sought in this job description? Reply only with the role/title, if not found, infer it, but avoid adding extra details; go straight to the point."
        retrieval_query = "Job title"
        logger.debug("Starting role/title extraction.")
        return self._extract_information(question, retrieval_query)
    
    def extract_location(self) -> str:
        """
        Extracts the location from the job description.
        Returns:
            str: The extracted location.
        """
        question = "What is the location mentioned in this job description? Reply only with the location, if not found, infer it, but avoid adding extra details; go straight to the point."
        retrieval_query = "Location"
        logger.debug("Starting location extraction.")
        return self._extract_information(question, retrieval_query)
    
    def extract_recruiter_email(self) -> str:
        """
        Extracts the recruiter's email from the job description.
        Returns:
            str: The extracted recruiter's email.
        """
        question = "What is the recruiter's email address in this job description? Reply only with the email, if not found, infer it, but avoid adding extra details; go straight to the point."
        retrieval_query = "Recruiter email"
        logger.debug("Starting recruiter email extraction.")
        email = self._extract_information(question, retrieval_query)
        
        # Validate the extracted email using regex
        email_regex = r'[\w\.-]+@[\w\.-]+\.\w+'
        if re.match(email_regex, email):
            logger.debug("Valid recruiter's email.")
            return email
        else:
            logger.warning("Invalid or not found recruiter's email.")
            return ""
 
