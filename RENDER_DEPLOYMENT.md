# Deploying ROXIN Studio to Render

Follow these steps to deploy your ROXIN Studio application on Render:

## Step 1: Create a Render Account
- Go to [render.com](https://render.com/) and sign up for an account or log in.

## Step 2: Connect Your Repository
1. Create a Git repository for your project if you haven't already.
2. Push your code to GitHub, GitLab, or Bitbucket.
3. Connect your repository to Render by clicking "New" and selecting "Web Service".

## Step 3: Configure Your Web Service
- **Name**: roxin-studio
- **Environment**: Python
- **Build Command**: `./build.sh`
- **Start Command**: `gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app`

## Step 4: Set Environment Variables
Add the following environment variables in the Render dashboard:

```
DATABASE_URL=postgresql://postgres.lgaybwinuhssjoyyyxkn:UNFtXoJfQsL5E1py@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
FLASK_SECRET_KEY=7841b4039475d02cd365bcbc294df9e4fb331b1675dae6e9
FLASK_APP=app.py
FLASK_ENV=production
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=ryabikinkirya90@gmail.com
MAIL_PASSWORD=ctni nchj orcs ftjz
MAIL_DEFAULT_SENDER=ryabikinkirya90@gmail.com
```

## Step 5: Deploy
- Click "Create Web Service" to start the deployment process.
- Render will clone your repository, install dependencies, and start your application.

## Step 6: Verify Deployment
- Once deployed, Render will provide a URL to access your application (e.g., https://roxin-studio.onrender.com).
- Verify that all features are working correctly, including:
  - User authentication (login/register)
  - Password recovery system
  - Order management
  - Chat functionality with Socket.IO
  - Admin panel functionality

## Troubleshooting
- If you encounter any issues, check the Render logs in the dashboard.
- Ensure your PostgreSQL database is properly configured and accessible from Render.
- If Socket.IO connections fail, ensure your client is connecting to the correct URL.

## Notes for ROXIN Studio Specific Features
- The password reset functionality should work automatically with the configured email settings.
- Ensure the database connection is working by testing the login and registration features.
- Socket.IO connections may need to be updated to use your Render domain for production.
