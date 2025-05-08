# ROXIN Studio

A Flask-based web application with PostgreSQL database and Socket.IO integration.

## Deployment Instructions

This application can be deployed to platforms that support Python web applications with PostgreSQL databases:

### Option 1: Heroku Deployment

1. Create a Heroku account if you don't have one
2. Install the Heroku CLI: https://devcenter.heroku.com/articles/heroku-cli
3. Login to Heroku:
   ```
   heroku login
   ```
4. Create a new Heroku app:
   ```
   heroku create roxin-studio
   ```
5. Add a PostgreSQL database:
   ```
   heroku addons:create heroku-postgresql:hobby-dev
   ```
6. Set environment variables:
   ```
   heroku config:set FLASK_SECRET_KEY=your-secret-key
   heroku config:set FLASK_ENV=production
   ```
7. Set email configuration for password reset:
   ```
   heroku config:set MAIL_SERVER=smtp.gmail.com
   heroku config:set MAIL_PORT=587
   heroku config:set MAIL_USE_TLS=True
   heroku config:set MAIL_USERNAME=your_email@gmail.com
   heroku config:set MAIL_PASSWORD=your_app_password
   heroku config:set MAIL_DEFAULT_SENDER=your_email@gmail.com
   ```
8. Deploy the application:
   ```
   git init
   git add .
   git commit -m "Initial commit"
   git push heroku master
   ```

### Option 2: Render Deployment

1. Create a Render account
2. Create a new Web Service and select your GitHub repository
3. Choose "Python" as the environment
4. Set the build command: `pip install -r requirements.txt`
5. Set the start command: `gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app`
6. Add the required environment variables in the Render dashboard
7. Create a PostgreSQL database service in Render
8. Connect your web service to the PostgreSQL database using the provided connection string

### Local Development

1. Create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up your .env file with the required environment variables
4. Run the application:
   ```
   python app.py
   ```

## Environment Variables

Make sure to set these environment variables:

- `DATABASE_URL`: PostgreSQL connection string
- `FLASK_SECRET_KEY`: Secret key for Flask sessions
- `FLASK_ENV`: Set to "production" for deployment
- `MAIL_SERVER`: SMTP server for sending emails
- `MAIL_PORT`: SMTP port
- `MAIL_USE_TLS`: Whether to use TLS
- `MAIL_USERNAME`: Email username
- `MAIL_PASSWORD`: Email password
- `MAIL_DEFAULT_SENDER`: Default sender email
