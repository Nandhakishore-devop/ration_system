# Ration System

## Problem Statement
Many rural women lose significant time and effort visiting government ration shops due to unpredictable crowd levels, long queues, and lack of timely information about item availability. This leads to wasted labor, repeated visits, and reduced daily productivity. To address this issue, the proposed system enables ration shop owners to update queue status (empty, manageable, or crowded) and daily available items through a simple interface, which is then automatically shared with registered users via Tamil SMS. By combining periodic updates with basic data analysis to suggest the best visiting times, the system aims to reduce waiting time, improve service accessibility, and provide a practical low-technology solution that works even for users without smartphones.

## Features
- Log queue status (e.g., waiting, served).
- Track items distributed.
- SQLite database integration for data persistence.
- Simple dashboard interface.

## Prerequisites
- Python 3.x
- pip

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd ration_system
   ```

2. **Set up virtual environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment:**
   - **Windows:**
     ```bash
     .\venv\Scripts\activate
     ```
   - **macOS/Linux:**
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. **Run the application:**
   ```bash
   python app.py
   ```

2. **Access the dashboard:**
   Open your browser and navigate to `http://127.0.0.1:5000/`.

3. **Initialize Database:**
   The database (`database.db`) is automatically initialized when you run the application for the first time.

## Project Structure
- `app.py`: Main Flask application and database logic.
- `requirements.txt`: List of Python dependencies.
- `templates/`: HTML templates for the frontend.
- `database.db`: SQLite database (auto-generated).
