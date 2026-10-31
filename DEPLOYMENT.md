# Deploying to AWS EC2 (optional)

You do NOT need to deploy this project. It runs fully with `docker compose up -d --build`,
and it has no CI/CD pipeline by default. Follow this guide only if you want a live demo.

## Memory and ports
- A 1 GB instance running BOTH the URL shortener stack and this stack will be tight.
  Either stop the other stack (`cd ~/url-shortener && docker compose stop`) or use a
  larger instance (which costs more credit). Add swap (see the URL shortener's DEPLOYMENT.md).
- This project uses different host ports on purpose: app 5001, database 5433, Redis 6380.
- In the EC2 security group, add **Custom TCP 5001** from Anywhere. Do NOT open 5433 or 6380.

## Steps
1. Push this project to its own GitHub repo (public, or set up a deploy key for a private one).
2. On the server, clone it into a folder named `rag-chatbot-api`:

       git clone https://github.com/<your-username>/<your-repo>.git rag-chatbot-api
       cd rag-chatbot-api

3. Create the `.env` file ON THE SERVER (it is not in Git):

       cp .env.example .env
       nano .env          # paste your API key, then Ctrl+O, Enter, Ctrl+X
       chmod 600 .env

4. Start it: `docker compose up -d --build`
5. Test from your laptop: `http://<EC2_PUBLIC_IP>:5001/health`

To update later: SSH in, then `cd ~/rag-chatbot-api && git pull && docker compose up -d --build`.

## Notes
- Because `.env` lives only on the server, the API key never goes into Git.
- If the public IP changes (Stop then Start), use the new IP in Postman.
- Plain HTTP on port 5001 is fine for a demo. For anything real, put Nginx with HTTPS in front.
- Anyone with the URL can call `/ask` and spend your OpenAI credit. Keep auto-reload off,
  and consider adding an API key header before sharing the link publicly.
- OpenAI usage is billed separately from AWS.

## Optional: automatic deploys with GitHub Actions
Not included by default. To add it, put the secrets `EC2_HOST`, `EC2_USER` and
`EC2_SSH_KEY` in the repo settings, and create `.github/workflows/ci-cd.yml`:

    name: CI/CD
    on:
      push:
        branches: [main]
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with:
              python-version: "3.12"
          - run: pip install -r requirements-dev.txt
          - run: pytest -v
      deploy:
        needs: test
        runs-on: ubuntu-latest
        steps:
          - name: Deploy to EC2 over SSH
            env:
              EC2_HOST: ${{ secrets.EC2_HOST }}
              EC2_USER: ${{ secrets.EC2_USER }}
              EC2_SSH_KEY: ${{ secrets.EC2_SSH_KEY }}
            run: |
              mkdir -p ~/.ssh
              echo "$EC2_SSH_KEY" > ~/.ssh/deploy_key
              chmod 600 ~/.ssh/deploy_key
              ssh-keyscan -H "$EC2_HOST" >> ~/.ssh/known_hosts
              ssh -i ~/.ssh/deploy_key "$EC2_USER@$EC2_HOST" \
                "cd ~/rag-chatbot-api && git pull origin main && docker compose up -d --build"
