import base64
from pathlib import Path
import inquirer
from selenium import webdriver
from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
from src.resume_schemas.resume import Resume
from src.logging import logger
from src.utils.chrome_utils import init_browser

class ResumeMaker():

    def create_cover_letter(parameters: dict, llm_api_key: str):
        """
        Logic to create a CV.
        """
        try:
            logger.info("Generating a CV based on provided parameters.")

            # Carica il resume in testo semplice
            with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
                plain_text_resume = file.read()

            style_manager = StyleManager()
            available_styles = style_manager.get_styles()

            if not available_styles:
                logger.warning("No styles available. Proceeding without style selection.")
            else:
                # Present style choices to the user
                choices = style_manager.format_choices(available_styles)
                questions = [
                    inquirer.List(
                        "style",
                        message="Select a style for the resume",
                        choices=choices,
                    )
                ]
                style_answer = inquirer.prompt(questions)
                if style_answer and "style" in style_answer:
                    selected_choice = style_answer["style"]
                    for style_name, (file_name, author_link) in available_styles.items():
                        if selected_choice.startswith(style_name):
                            style_manager.set_selected_style(style_name)
                            logger.info(f"Selected style: {style_name}")
                            break
                else:
                    logger.warning("No style selected. Proceeding with default style.")
            questions = [
                inquirer.Text('job_url', message="Please enter the URL of the job description")
            ]
            answers = inquirer.prompt(questions)
            job_url = answers.get('job_url')
            resume_generator = ResumeGenerator()
            resume_object = Resume(plain_text_resume)
            #options = webdriver.ChromeOptions()
            #options.add_argument('--headless')
            #driver = init_browser(options=options)
            driver = init_browser()
            resume_generator.set_resume_object(resume_object)
            
            # Create the ResumeFacade
            resume_facade = ResumeFacade(            
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=Path("data_folder/output"),
            )
            
            # Initialize the Resume Generator
            resume_facade.set_driver(driver)
            resume_facade.link_to_job(job_url)
            result_base64, suggested_name = resume_facade.util_create_cover_letter()         

            # Decodifica Base64 in dati binari
            try:
                pdf_data = base64.b64decode(result_base64)
            except base64.binascii.Error as e:
                logger.error("Error decoding Base64: %s", e)
                raise

            # Define the path to the output folder using `suggested_name`. Maybe include the current date?
            output_dir = Path(parameters["outputFileDirectory"]) / suggested_name
            # / {datetime.now().strftime('%Y-%m-%d')}

            # Crea la cartella se non esiste
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Cartella di output creata o già esistente: {output_dir}")
            except IOError as e:
                logger.error("Error creating output directory: %s", e)
                raise
            
            output_path = output_dir / "cover_letter.pdf"
            try:
                with open(output_path, "wb") as file:
                    file.write(pdf_data)
                logger.info(f"CV salvato in: {output_path}")
            except IOError as e:
                logger.error("Error writing file: %s", e)
                raise
        except Exception as e:
            logger.exception(f"An error occurred while creating the CV: {e}")
            raise

    def create_resume_pdf_tailored(parameters: dict, llm_api_key: str):
        """
        Logic to create a CV.
        """
        try:
            logger.info("Generating a CV based on provided parameters.")

            # Carica il resume in testo semplice
            with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
                plain_text_resume = file.read()

            style_manager = StyleManager()
            available_styles = style_manager.get_styles()

            if not available_styles:
                logger.warning("No styles available. Proceeding without style selection.")
            else:
                # Present style choices to the user
                choices = style_manager.format_choices(available_styles)
                questions = [
                    inquirer.List(
                        "style",
                        message="Select a style for the resume",
                        choices=choices,
                    )
                ]
                style_answer = inquirer.prompt(questions)
                if style_answer and "style" in style_answer:
                    selected_choice = style_answer["style"]
                    for style_name in available_styles.items():
                        if selected_choice.startswith(style_name[0]):
                            style_manager.set_selected_style(style_name[0])
                            logger.info(f"Selected style: {style_name[0]}")
                            break
                else:
                    logger.warning("No style selected. Proceeding with default style.")
            questions = [inquirer.Text('job_url', message="Please enter the URL of the job description")]
            answers = inquirer.prompt(questions)
            try: 
                job_url = answers.get('job_url')
            except:
                logger.error("No job URL provided, exiting...")
                quit()
            
            resume_generator = ResumeGenerator()
            resume_object = Resume(plain_text_resume)
            driver = init_browser()
            
            resume_generator.set_resume_object(resume_object)
            resume_facade = ResumeFacade(            
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=Path("data_folder/output"),
            )
            resume_facade.set_driver(driver)
            resume_facade.link_to_job(job_url)
            result_base64, suggested_name = resume_facade.util_create_resume_pdf_job_tailored()

            # Decodifica Base64 in dati binari
            try:
                pdf_data = base64.b64decode(result_base64)
            except base64.binascii.Error as e:
                logger.error("Error decoding Base64: %s", e)
                raise

            # Definisci il percorso della cartella di output utilizzando `suggested_name`
            output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

            # Crea la cartella se non esiste
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Cartella di output creata o già esistente: {output_dir}")
            except IOError as e:
                logger.error("Error creating output directory: %s", e)
                raise
            
            output_path = output_dir / "resume.pdf"
            try:
                with open(output_path, "wb") as file:
                    file.write(pdf_data)
                logger.info(f"CV salvato in: {output_path}")
            except IOError as e:
                logger.error("Error writing file: %s", e)
                raise
        except Exception as e:
            logger.exception(f"An error occurred while creating the CV: {e}")
            raise

    def create_resume_pdf(parameters: dict, llm_api_key: str):
        """
        Logic to create a CV.
        """
        try:
            logger.info("Generating a CV based on provided parameters.")

            # Load the plain text resume
            with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
                plain_text_resume = file.read()

            # Initialize StyleManager
            style_manager = StyleManager()
            available_styles = style_manager.get_styles()

            if not available_styles:
                logger.warning("No styles available. Proceeding without style selection.")
            else:
                # Present style choices to the user
                choices = style_manager.format_choices(available_styles)
                questions = [
                    inquirer.List(
                        "style",
                        message="Select a style for the resume",
                        choices=choices,
                    )
                ]
                style_answer = inquirer.prompt(questions)
                if style_answer and "style" in style_answer:
                    selected_choice = style_answer["style"]
                    for style_name, (file_name, author_link) in available_styles.items():
                        if selected_choice.startswith(style_name):
                            style_manager.set_selected_style(style_name)
                            logger.info(f"Selected style: {style_name}")
                            break
                else:
                    logger.warning("No style selected. Proceeding with default style.")

            # Initialize the Resume Generator
            resume_generator = ResumeGenerator()
            resume_object = Resume(plain_text_resume)

            # Making it headless, as it just generates the html and converts it to PDF
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            driver = init_browser(options=options)

            resume_generator.set_resume_object(resume_object)

            # Create the ResumeFacade
            resume_facade = ResumeFacade(
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=Path("data_folder/output"),
            )
            resume_facade.set_driver(driver)
            result_base64 = resume_facade.create_resume_pdf()

            # Decode Base64 to binary data
            try:
                pdf_data = base64.b64decode(result_base64)
            except base64.binascii.Error as e:
                logger.error("Error decoding Base64: %s", e)
                raise

            # Define the output directory using `suggested_name`
            output_dir = Path(parameters["outputFileDirectory"])

            # Write the PDF file
            output_path = output_dir / "resume_base.pdf"
            try:
                with open(output_path, "wb") as file:
                    file.write(pdf_data)
                logger.info(f"Resume saved at: {output_path}")
            except IOError as e:
                logger.error("Error writing file: %s", e)
                raise
        except Exception as e:
            logger.exception(f"An error occurred while creating the CV: {e}")
            raise
