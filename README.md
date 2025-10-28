# Utsulog - YouTube Chat Log Search Engine

Utsulog is a full-text search application for YouTube live stream chat logs. It consists of a batch processing system to collect chat data and a web interface to search and view the results.

## Features

- **Full-Text Search:** Quickly search through a vast amount of YouTube chat logs.
- **Timestamped Links:** Each search result links directly to the corresponding moment in the YouTube video.
- **Data Collection:** Automated batch scripts fetch video information and chat logs from specified YouTube channels.
- **Modern UI:** A responsive and user-friendly interface for searching and filtering results.

## System Architecture

The application is divided into two main components: the **Batch System** for data collection and the **Web Application** for user interaction.

### 1. Batch System (Data Collection)

The batch system runs periodically to gather the latest chat logs and index them into Elasticsearch.

```
┌───────────────────┐      ┌───────────────────┐      ┌───────────────────────┐      ┌─────────────────┐
│  get_videos.py    │───►│  get_chatlog.py   │───►│ import_chat_logs.py │───►│  Elasticsearch  │
└───────────────────┘      └───────────────────┘      └───────────────────────┘      └─────────────────┘
       │                      │                      │                                    ▲
       ▼                      ▼                      ▼                                    │
- Fetches video list     - Downloads chat logs  - Processes logs & bulk                  │
  from YouTube channel     for each video         inserts into Elasticsearch             │
  (using yt-dlp)           (using yt-dlp)                                                │
                                                                                         │
```

### 2. Web Application (Search & Display)

The web application allows users to search the indexed chat logs.

```
┌────────┐      ┌──────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  User  │◄───►│ Frontend (React) │◄───►│ API Server (FastAPI) │───►│  Elasticsearch  │
└────────┘      └──────────────────┘      └──────────────────┘      └─────────────────┘
     ▲              │      │                      │                      │
     │              │      │  - Receives query    │  - Searches index    │
     │              │      │  - Sends request     │    with query        │
     │              │      └──────────────────────►                      │
     │              │                                                    │
     └──────────────│─────── Returns search results (JSON) ◄────────────┘
                    │
                    ▼
              - Displays results
              - Generates timestamped links
```

## Technology Stack

- **Frontend:**
  - React
  - TypeScript
  - Vite
  - Tailwind CSS
- **API Server:**
  - Python 3.9
  - FastAPI
- **Batch Processing:**
  - Python 3.9
  - yt-dlp
- **Database / Search Engine:**
  - Elasticsearch
- **Infrastructure:**
  - Docker & Docker Compose
  - (Planned) AWS Fargate, S3, Elastic Cloud

## Local Development

### Prerequisites

- Git
- Docker
- Docker Compose

### Getting Started

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yazzu/utsulog.git
    cd utsulog
    ```

2.  **Set up environment variables:**
    The batch scripts require a YouTube Data API key. You will need to set this up if you intend to run the data collection scripts.

3.  **Start the development environment:**
    This command builds the containers and starts all services, including the frontend, API server, Elasticsearch, and Kibana.
    ```bash
    docker-compose up --build
    ```

4.  **Access the services:**
    - **Frontend Application:** [http://localhost:3000](http://localhost:3000)
    - **API Server:** [http://localhost:8000](http://localhost:8000)
    - **Kibana (for Elasticsearch):** [http://localhost:5601](http://localhost:5601)

The frontend and API services are configured with live reloading, so any changes you make to the source code will be reflected automatically.

## Directory Structure

```
.
├── api/          # FastAPI backend server
├── batch/        # Python scripts for data collection
├── frontend/     # React frontend application
├── chat_logs/    # (Generated) Raw chat log data
├── docker-compose.yml
└── README.md
```
