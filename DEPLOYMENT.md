# Deploying to AWS EC2

Same approach as the URL shortener project. Read these extra points first.

## Memory and ports
- A 1 GB instance running BOTH the URL shortener stack and this stack will be tight.
  Either stop the other stack (`cd ~/url-shortener && docker compose stop`) or use a
  larger instance (which costs more credit). Add swap (see the URL shortener's DEPLOYMENT.md).
- This project uses different host ports on purpose: app 5001, database 5433, Redis 6380.
- In the EC2 security group, add **Custom TCP 5001** from Anywhere. Do NOT open 5433 or 6380.

## Steps
1. Push this project to its own GitHub repo (public, or set up a deploy key for a private one).
2. On the server, clone it into a folder named `rag-chatbot-api` (the pipeline expects it):

       git clone https://github.com/<your-username>/<your-repo>.git rag-chatbot-api
       cd rag-chatbot-api

3. Create the `.env` file ON THE SERVER (it is not in Git):

       cp .env.example .env
       nano .env          # paste your API key, then Ctrl+O, Enter, Ctrl+X
       chmod 600 .env

4. Start it: `docker compose up -d --build`
5. Test from your laptop: `http://<EC2_PUBLIC_IP>:5001/health`
6. The pipeline reuses the same GitHub secrets as the URL shortener
   (`EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`). Add them to this repo as well.
   Pushes to `main` then deploy automatically.

## Notes
- Because `.env` lives only on the server, the API key never goes into Git or the CI logs.
- If the public IP changes (Stop then Start), update the `EC2_HOST` secret.
- Plain HTTP on port 5001 is fine for a demo. For anything real, put Nginx with HTTPS in front.
- OpenAI usage is billed separately from AWS. Keep your OpenAI usage limit and auto-reload settings as they are.
