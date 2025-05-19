"""
This module is used to store the global configuration of the application.
"""
# settings/config.py
from pathlib import Path

class GlobalConfig:
    def __init__(self):
        self.STYLES_DIRECTORY: Path = None
        self.LOG_OUTPUT_FILE_PATH: Path = None
        self.API_KEY: str = None
        self.LLM_MODEL_TYPE: str = None
        self.LLM_MODEL: str = None
        self.html_template = """
                            <!DOCTYPE html>
                            <html lang="en">
                            <head>
                                <meta charset="UTF-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                <title>Resume</title>
                                <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&display=swap" rel="stylesheet" />
                                <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&display=swap" rel="stylesheet" /> 
                                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css" /> 
                                    <style>
                                        $style_css
                                    </style>
                            </head>
                            <body>
                            $body
                            </body>
                            </html>
                            """

global_config = GlobalConfig()
