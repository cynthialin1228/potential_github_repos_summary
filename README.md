## 1. Clone this repo
```
git clone https://github.com/cynthialin1228/potential_github_repos_summary.git
```

## 2. Create Conda
```
conda create -n github_repo_news python=3.10
conda activate github_repo_news
```

## 3. Install requirements
```
pip3 install -r requirements.txt
```

## 4. Create .env file
```
GITHUB_TOKEN="your github (classic) token"
GEMINI_API_KEY="your gemini key"
```

## 5. Check the repo searching condition
This version searches for repo created in last 31 days, and with the most stars.
Modify it if needed.

## 6. Execute and get results in the "output" directory.
```
python3 get_summary.py
```