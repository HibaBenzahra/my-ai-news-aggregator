my-ai-news-aggregator/
├── agent/
│   └── digest_prompt.md
├── aggregator/
│   ├── __init__.py
│   ├── config.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── session.py
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── youtube.py
│   │   └── blog.py
│   ├── digest.py
│   ├── email_sender.py
│   └── scheduler.py
├── docker/
│   ├── docker-compose.yml
│   └── Dockerfile
├── main.py
├── pyproject.toml
├── .env.example
└── README.md