# Excel at Sheets

A Flask-based web application that allows users to interact with Excel spreadsheets through a chat interface, providing analysis and visualization capabilities.

## Features

- Upload Excel spreadsheets (.xlsx) for analysis
- Chat with your spreadsheet data (ask questions about cells, formulas, etc.)
- Generate comprehensive analysis reports
- Create data visualizations with various chart types
- Generate AI-powered custom visualizations based on your data

## Setup

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your OpenAI API key:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```
4. Run the application:
   ```
   python app.py
   ```

## Usage

1. Upload an Excel spreadsheet using the file upload form
2. Ask questions about your data in the chat interface
3. Get interactive plot suggestions tailored to your data
4. Generate AI visualizations by clicking on plot ideas
5. Generate comprehensive analysis reports with charts

## AI-Powered Visualizations

The application includes a feature to generate custom visualizations using OpenAI's DALL-E API. 
When you click on one of the suggested plot ideas, the system will:

1. Extract relevant data from your spreadsheet
2. Generate a prompt based on the data and the plot idea
3. Use OpenAI's image generation API to create a custom visualization
4. Save the visualization locally and display it in the chat

This feature requires a valid OpenAI API key with access to the DALL-E model. 