from flask import Flask
import os
from celery import Celery, Task
from modules.models import Player, Match, Game, Play, Pick, Draft, GameActions, Removed, CardsPlayed
from flask import request, url_for, flash, render_template, redirect
from flask_login import login_user, login_required, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from modules.extensions import db, mail, login_manager
from debug_routes import debug_bp

DB_NAME = 'database.db'

def make_celery(app):
	celery = Celery(
		app.import_name,
		backend=app.config['CELERY_RESULT_BACKEND'],
		broker=app.config['CELERY_BROKER_URL']
	)
	celery.conf.update(app.config)

	class ContextTask(celery.Task):
		def __call__(self, *args, **kwargs):
			with app.app_context():
				return self.run(*args, **kwargs)

	celery.Task = ContextTask
	return celery

def create_app():
	app = Flask(__name__)
	
	# Determine environment and load appropriate config
	env = os.environ.get('FLASK_ENV', 'development')
	if env == 'development' or env == 'local':
		app.config.from_pyfile('local-dev/local_config.cfg')
		print("Running in LOCAL/DEVELOPMENT mode")
	else:
		app.config.from_pyfile('static/config.cfg')
		print("Running in PRODUCTION mode")
	
	# Override with environment variables if they exist (for production)
	app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", app.config.get('SECRET_KEY'))
	app.config['MAIL_SERVER'] = os.environ.get("MAIL_SERVER", app.config.get('MAIL_SERVER'))
	app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME", app.config.get('MAIL_USERNAME'))
	app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD", app.config.get('MAIL_PASSWORD'))
	app.config['MAIL_DEFAULT_SENDER'] = os.environ.get("MAIL_DEFAULT_SENDER", app.config.get('MAIL_DEFAULT_SENDER'))
	app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("SQLALCHEMY_DATABASE_URI", app.config.get('SQLALCHEMY_DATABASE_URI'))
	app.config['CELERY_RESULT_BACKEND'] = os.environ.get("CELERY_RESULT_BACKEND", app.config.get('CELERY_RESULT_BACKEND'))
	app.config['CELERY_BROKER_URL'] = os.environ.get("CELERY_BROKER_URL", app.config.get('CELERY_BROKER_URL'))
	app.config['URL_SAFETIMEDSERIALIZER'] = os.environ.get("URL_SAFETIMEDSERIALIZER", app.config.get('URL_SAFETIMEDSERIALIZER'))
	app.config['EMAIL_CONFIRMATION_SALT'] = os.environ.get("EMAIL_CONFIRMATION_SALT", app.config.get('EMAIL_CONFIRMATION_SALT'))
	app.config['RESET_PASSWORD_SALT'] = os.environ.get("RESET_PASSWORD_SALT", app.config.get('RESET_PASSWORD_SALT'))

	# Initialize extensions
	mail.init_app(app)
	db.init_app(app)

	from modules.views import views
	from modules.auth import auth

	app.register_blueprint(views, url_prefix='/')
	app.register_blueprint(auth, url_prefix='/')
	app.register_blueprint(debug_bp)

	from modules.models import Player

	with app.app_context():
		db.create_all()

	login_manager.login_view = 'views.login'
	login_manager.init_app(app)

	@login_manager.user_loader
	def load_user(uid):
		return Player.query.get(int(uid))

	return app

app = create_app()
celery = make_celery(app)
celery.set_default()
app.app_context().push()

#mail = Mail(app)

if __name__ == '__main__':
	# Set environment for local development
	os.environ['FLASK_ENV'] = 'local'
	app.run(host="0.0.0.0", port=8000, debug=True)