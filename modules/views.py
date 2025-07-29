from flask import render_template, request, Blueprint, flash, redirect, send_file, Response, jsonify, redirect, url_for, current_app, session, after_this_request
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, create_engine, desc, select, and_, asc
from sqlalchemy.sql.expression import not_
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import datetime
from modules.models import Player, Match, Game, Play, Pick, Draft, GameActions, Removed, CardsPlayed, TaskHistory
from modules.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import os
import io
import time
import tempfile
import shutil
from modules import modo
import pickle
import math 
import pandas as pd
import zipfile
import requests
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, generate_blob_sas, BlobSasPermissions
from azure.core.exceptions import ResourceNotFoundError
import pytz
import json
import logging
import threading
#logging.getLogger("smtplib").setLevel(logging.ERROR)
#logging.getLogger("celery").setLevel(logging.ERROR)

# Debug logging function
def debug_log(message):
	"""Log debug messages to both console and file"""
	timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	log_message = f"[{timestamp}] {message}"
	
	# Print to console
	print(log_message)
	
	# Write to log file
	try:
		log_dir = os.path.join('local-dev', 'data', 'logs')
		os.makedirs(log_dir, exist_ok=True)
		log_file = os.path.join(log_dir, 'debug_log.txt')
		
		with open(log_file, 'a', encoding='utf-8') as f:
			f.write(log_message + '\n')
	except Exception as e:
		debug_log(f"Warning: Could not write to log file: {e}")

page_size = 20

# Initialize Azure clients only if connection string is available
try:
    azure_connection_string = os.environ.get('AZURE_CONNECTION_STRING')
    if azure_connection_string:
        blob_service_client = BlobServiceClient.from_connection_string(azure_connection_string)
        log_container_client = blob_service_client.get_container_client(os.environ.get('LOG_CONTAINER_NAME'))
        export_container_client = blob_service_client.get_container_client(os.environ.get('EXPORT_CONTAINER_NAME'))
    else:
        blob_service_client = None
        log_container_client = None
        export_container_client = None
        debug_log("Azure connection string not found - running in local mode")
except Exception as e:
    blob_service_client = None
    log_container_client = None
    export_container_client = None
    debug_log(f"Failed to initialize Azure clients: {e}")

s = URLSafeTimedSerializer(os.environ.get("URL_SAFETIMEDSERIALIZER", "dev-secret-key"))
views = Blueprint('views', __name__)

def get_input_options():
	"""Load input options from local file"""
	input_options_file = os.path.join('auxiliary', 'INPUT_OPTIONS.txt')
	
	if not os.path.exists(input_options_file):
		debug_log(f"Input options file not found: {input_options_file}")
		return {}
	
	in_header = False
	in_instr = True
	input_options = {}
	x = ""
	y = []
	
	try:
		with open(input_options_file, 'r', encoding='utf-8', errors='ignore') as f:
			lines = f.read().replace('\x00', '').split('\n')
			
		for i in lines:
			if i == "-----------------------------":
				if in_instr:
					in_instr = False
				in_header = not in_header
				if in_header == False:
					x = last.split(":")[0].split("# ")[1]
				elif x != "":
					input_options[x] = y
					y = []                        
			elif (in_header == False) and (i != "") and (in_instr == False):
				y.append(i)
			last = i
		
		debug_log(f"Loaded input options with {len(input_options)} categories from local file")
		return input_options
		
	except Exception as e:
		debug_log(f"Error reading input options file: {e}")
		return {}
def get_multifaced_cards():
	"""Load multifaced cards from local file"""
	multifaced_file = os.path.join('auxiliary', 'MULTIFACED_CARDS.txt')
	
	if not os.path.exists(multifaced_file):
		debug_log(f"Multifaced cards file not found: {multifaced_file}")
		return {}
	
	multifaced_cards = {}
	try:
		with open(multifaced_file, 'r', encoding='utf-8', errors='ignore') as f:
			lines = f.read().replace('\x00', '').split('\n')
			
		for i in lines:
			if i.isupper():
				multifaced_cards[i] = {}
				last = i
			if ' // ' in i:
				multifaced_cards[last][i.split(' // ')[0]] = i.split(' // ')[1]
		
		debug_log(f"Loaded {len(multifaced_cards)} multifaced card categories from local file")
		return multifaced_cards
		
	except Exception as e:
		debug_log(f"Error reading multifaced cards file: {e}")
		return {}
def get_all_decks():
	"""Load all decks from local pickle file"""
	decks_file = os.path.join('auxiliary', 'ALL_DECKS')
	
	if not os.path.exists(decks_file):
		debug_log(f"All decks file not found: {decks_file}")
		return {}
	
	try:
		with open(decks_file, 'rb') as f:
			all_decks = pickle.load(f)
		
		debug_log(f"Loaded {len(all_decks) if isinstance(all_decks, dict) else 'unknown'} decks from local file")
		return all_decks
		
	except Exception as e:
		debug_log(f"Error reading all decks file: {e}")
		return {}
def build_cards_played_db(uid):
	#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Building cards played database for user {uid}")
	
	try:
		# Ensure global variables are loaded
		ensure_data_loaded()
		#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Global variables loaded")
		
		query = db.session.query(Match.match_id).filter_by(uid=uid).distinct()
		match_ids = [value[0] for value in query.all()]
		#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Found {len(match_ids)} unique match IDs")
		
		cards_added = 0
		for i in match_ids:
			#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Processing match {i}")
			
			if CardsPlayed.query.filter_by(uid=uid, match_id=i).first():
				#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Match {i} already exists, skipping")
				continue
				
			try:
				players = [value[0] for value in db.session.query(Play.casting_player).filter_by(uid=uid, match_id=i).distinct().all()]
				
				if len(players) < 2:
					#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Match {i} has insufficient players ({len(players)}), skipping")
					continue

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[0], action='Casts').distinct()
				plays1 = [value[0] for value in query.all()]
				plays1 = modo.clean_card_set(set(plays1),multifaced)

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[1], action='Casts').distinct()
				plays2 = [value[0] for value in query.all()]
				plays2 = modo.clean_card_set(set(plays2),multifaced)

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[0], action='Land Drop').distinct()
				lands1 = [value[0] for value in query.all()]
				lands1 = modo.clean_card_set(set(lands1),multifaced)

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[1], action='Land Drop').distinct()
				lands2 = [value[0] for value in query.all()]
				lands2 = modo.clean_card_set(set(lands2),multifaced)

				cards_played = CardsPlayed(uid=uid,
											match_id=i,
											casting_player1=players[0],
											casting_player2=players[1],
											plays1=sorted(list(plays1),reverse=False),
											plays2=sorted(list(plays2),reverse=False),
											lands1=sorted(list(lands1),reverse=False),
											lands2=sorted(list(lands2),reverse=False))
				db.session.add(cards_played)
				cards_added += 1
				#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Added cards played for match {i}")
				
			except Exception as e:
				#debug_log(f"🔍 BUILD CARDS PLAYED ERROR: Failed to process match {i}: {e}")
				continue
		
		# Single commit at the end for better performance
		if cards_added > 0:
			try:
				db.session.commit()
				#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Successfully committed {cards_added} cards played records")
			except Exception as e:
				#debug_log(f"🔍 BUILD CARDS PLAYED ERROR: Failed to commit: {e}")
				db.session.rollback()
		else:
			debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: No new cards played records to add")
			
	except Exception as e:
		#debug_log(f"🔍 BUILD CARDS PLAYED CRITICAL ERROR: {e}")
		try:
			db.session.rollback()
		except:
			pass
def update_draft_win_loss(uid, username, draft_id):
	if draft_id != 'NA':
		draft_record = Draft.query.filter_by(uid=uid, draft_id=draft_id, hero=username).first()
		wins = Match.query.filter_by(uid=uid, draft_id=draft_id, p1=username, match_winner='P1').count()
		losses = Match.query.filter_by(uid=uid, draft_id=draft_id, p1=username, match_winner='P2').count()
		draft_record.match_wins = wins
		draft_record.match_losses = losses
		try:
			db.session.commit()
		except:
			db.session.rollback()
def get_logtype_from_filename(filename):
	if ('Match_GameLog_' in filename) and (len(filename) >= 30) and ('.dat' in filename):
		return 'GameLog'
	if (filename.count('.') != 3) or (filename.count('-') != 4) or ('.txt' not in filename):
		return 'NA'
	elif (len(filename.split('-')[1].split('.')[0]) != 4) or (len(filename.split('-')[2]) != 4):
		return 'NA'
	else:
		return 'DraftLog'

@shared_task(bind=True, base=AbortableTask)
def process_logs(self, data):
	def extract_zip_file(zip_ref, path):
		skipped = 0
		uploaded = 0
		new_files = []
		replaced_files = []
		skipped_files = []
		
		# Create local storage directory if it doesn't exist
		if log_container_client is None:  # Local mode
			local_storage_dir = os.path.join('local-dev', 'data', 'uploads', str(data['user_id']))
			os.makedirs(local_storage_dir, exist_ok=True)
			debug_log(f"🔍 EXTRACT DEBUG: Using local storage: {local_storage_dir}")
		
		debug_log(f"🔍 EXTRACT DEBUG: Processing {len(zip_ref.infolist())} files from zip")
		for member in zip_ref.infolist():
			debug_log(f"🔍 EXTRACT DEBUG: Processing zip member: {member.filename}")
			
			logtype = get_logtype_from_filename(member.filename)
			debug_log(f"🔍 EXTRACT DEBUG: File {member.filename} has logtype: {logtype}")
			
			if get_logtype_from_filename(member.filename) == 'NA':
				debug_log(f"🔍 EXTRACT DEBUG: Skipping {member.filename} - logtype is NA")
				skipped += 1
				continue
			
			if log_container_client is None:  # Local file storage
				# Local file storage logic
				local_file_path = os.path.join(local_storage_dir, member.filename)
				new_mtime = time.strftime('%Y%m%d%H%M', member.date_time + (0, 0, -1))
				debug_log(f"🔍 EXTRACT DEBUG: Local file path: {local_file_path}")
				debug_log(f"🔍 EXTRACT DEBUG: New file mtime: {new_mtime}")
				
				# Check if file exists locally
				if os.path.exists(local_file_path):
					debug_log(f"🔍 EXTRACT DEBUG: File exists locally: {local_file_path}")
					# Read existing metadata from a companion .meta file
					meta_file = local_file_path + '.meta'
					if os.path.exists(meta_file):
						with open(meta_file, 'r') as f:
							existing_mtime = f.read().strip()
						debug_log(f"🔍 EXTRACT DEBUG: Existing mtime: {existing_mtime}, New mtime: {new_mtime}")
						if new_mtime >= existing_mtime:
							debug_log(f"🔍 EXTRACT DEBUG: Skipping {member.filename} - new mtime >= existing mtime")
							skipped_files.append(member.filename.split('/')[-1])
							skipped += 1
							continue
						else:
							debug_log(f"🔍 EXTRACT DEBUG: Replacing {member.filename} - new mtime < existing mtime")
							# Replace with newer file
							zip_ref.extract(member, local_storage_dir)
							# Move file to final location and save metadata
							extracted_path = os.path.join(local_storage_dir, member.filename)
							if extracted_path != local_file_path:
								os.rename(extracted_path, local_file_path)
							with open(meta_file, 'w') as f:
								f.write(new_mtime)
							replaced_files.append(member.filename.split('/')[-1])
							uploaded += 1
					else:
						debug_log(f"🔍 EXTRACT DEBUG: File exists but no metadata - replacing {member.filename}")
						# File exists but no metadata, replace it
						zip_ref.extract(member, local_storage_dir)
						extracted_path = os.path.join(local_storage_dir, member.filename)
						if extracted_path != local_file_path:
							os.rename(extracted_path, local_file_path)
						with open(local_file_path + '.meta', 'w') as f:
							f.write(new_mtime)
						replaced_files.append(member.filename.split('/')[-1])
						uploaded += 1
				else:
					debug_log(f"🔍 EXTRACT DEBUG: New file - extracting {member.filename}")
					# New file
					zip_ref.extract(member, local_storage_dir)
					extracted_path = os.path.join(local_storage_dir, member.filename)
					if extracted_path != local_file_path:
						os.rename(extracted_path, local_file_path)
					with open(local_file_path + '.meta', 'w') as f:
						f.write(new_mtime)
					new_files.append(member.filename.split('/')[-1])
					uploaded += 1
			else:  # Azure Blob Storage logic (original)
				extracted_file_name = path + member.filename
				blob_client = log_container_client.get_blob_client(extracted_file_name)
				try:
					# File exists in Azure Blob Storage.
					existing_mtime = blob_client.get_blob_properties()['metadata']['original_mod_time']
					new_mtime = time.strftime('%Y%m%d%H%M', member.date_time + (0, 0, -1))
					if new_mtime >= existing_mtime:
						skipped_files.append(member.filename.split('/')[-1])
						skipped += 1
					else:
						# Replace newer file with older file
						zip_ref.extract(member, os.getcwd())
						with open(member.filename, 'rb') as file_to_upload:
							blob_client.upload_blob(file_to_upload, metadata={'original_mod_time':new_mtime}, overwrite=True)
						replaced_files.append(member.filename.split('/')[-1])
						os.remove(member.filename)
						uploaded += 1
				except ResourceNotFoundError:
					# New file.
					file_mod_time = time.strftime('%Y%m%d%H%M', member.date_time + (0, 0, -1))
					zip_ref.extract(member, os.getcwd())
					with open(member.filename, 'rb') as file_to_upload:
						blob_client.upload_blob(file_to_upload, metadata={'original_mod_time':file_mod_time})
					new_files.append(member.filename.split('/')[-1])
					os.remove(member.filename)
					uploaded += 1
		debug_log(f"🔍 EXTRACT DEBUG: Extraction complete - skipped: {skipped}, uploaded: {uploaded}")
		debug_log(f"🔍 EXTRACT DEBUG: new_files: {new_files}")
		debug_log(f"🔍 EXTRACT DEBUG: replaced_files: {replaced_files}")
		debug_log(f"🔍 EXTRACT DEBUG: skipped_files: {skipped_files}")
		return {'skipped':skipped,'uploaded':uploaded, 'new_files':new_files, 'replaced_files':replaced_files, 'skipped_files':skipped_files}
	
	counts = {
		'new_matches':0,
		'new_games':0,
		'new_plays':0,
		'new_drafts':0,
		'new_picks':0,
		'matches_replaced':0,
		'games_replaced':0,
		'plays_replaced':0,
		'drafts_replaced':0,
		'picks_replaced':0,
		'gamelogs_skipped_error':0,
		'gamelogs_skipped_removed':0,
		'gamelogs_skipped_empty':0,
		'draftlogs_skipped_error':0,
		'draftlogs_skipped_removed':0,
		'draftlogs_skipped_empty':0,
		'total_gamelogs':0,
		'total_draftlogs':0,
	}
	game_errors = {}
	draft_errors = {}
	uid = data['user_id']
	submit_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	error_code = None
	file_stream = io.BytesIO(data['file_stream'])

	with zipfile.ZipFile(file_stream, 'r') as zip_ref:
		upload_dict = extract_zip_file(zip_ref, str(uid) + '\\')
	
	try:
		# Get list of files to process based on storage type
		files_to_process = []
		
		if log_container_client is None:  # Local file storage
			local_storage_dir = os.path.join('local-dev', 'data', 'uploads', str(uid))
			debug_log(f"🔍 DEBUG: Looking for files in: {local_storage_dir}")
			debug_log(f"🔍 DEBUG: Directory exists: {os.path.exists(local_storage_dir)}")
			if os.path.exists(local_storage_dir):
				all_files = os.listdir(local_storage_dir)
				debug_log(f"🔍 DEBUG: Found {len(all_files)} total files: {all_files}")
				debug_log(f"🔍 DEBUG: Skipped files from upload_dict: {upload_dict['skipped_files']}")
				for filename in all_files:
					debug_log(f"🔍 DEBUG: Processing file: {filename}")
					if filename.endswith('.meta'):  # Skip metadata files
						debug_log(f"🔍 DEBUG: Skipping {filename} (metadata file)")
						continue
					if filename in upload_dict['skipped_files']:
						debug_log(f"🔍 DEBUG: Skipping {filename} (in skipped_files)")
						continue
					
					local_file_path = os.path.join(local_storage_dir, filename)
					meta_file_path = local_file_path + '.meta'
					
					# Read metadata
					if os.path.exists(meta_file_path):
						with open(meta_file_path, 'r') as f:
							mtime = f.read().strip()
					else:
						mtime = '202301010000'  # Default fallback
					
					log_type = get_logtype_from_filename(filename)
					debug_log(f"🔍 DEBUG: File {filename} detected as log_type: '{log_type}'")
					if log_type in ['GameLog', 'DraftLog']:
						debug_log(f"🔍 DEBUG: Adding {filename} to files_to_process")
						files_to_process.append({
							'filename': filename,
							'path': local_file_path,
							'mtime': mtime,
							'storage_type': 'local',
							'log_type': log_type
						})
					else:
						debug_log(f"🔍 DEBUG: Skipping {filename} - log_type '{log_type}' not in ['GameLog', 'DraftLog']")
			else:
				debug_log(f"🔍 DEBUG: Local storage directory does not exist: {local_storage_dir}")
		else:  # Azure Blob Storage
			for blob in log_container_client.list_blobs():
				filename = blob.name.split('/')[-1]
				if filename in upload_dict['skipped_files']:
					continue
				try:
					blob_uid = blob.name.split('/')[0]
				except:
					blob_uid = 0

				if (get_logtype_from_filename(filename) in ['GameLog', 'DraftLog']) and (str(uid) == blob_uid):
					blob_client = blob_service_client.get_blob_client(container=os.environ.get('LOG_CONTAINER_NAME'), blob=blob.name)
					blob_properties = blob_client.get_blob_properties()
					mtime = blob_properties['metadata']['original_mod_time']
					
					files_to_process.append({
						'filename': filename,
						'blob_client': blob_client,
						'mtime': mtime,
						'storage_type': 'azure',
						'log_type': get_logtype_from_filename(filename)
					})
		
		# Now process all files with unified logic
		debug_log(f"🔍 Processing {len(files_to_process)} files")
		
		# Database and email operations - get Flask app from Celery BEFORE processing files
		from app import create_app
		app = create_app()
		
		with app.app_context():
			for file_info in files_to_process:
				filename = file_info['filename']
				mtime = file_info['mtime']
				log_type = file_info['log_type']
				
				# Read file content based on storage type
				if file_info['storage_type'] == 'local':
					with open(file_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
						initial = f.read().replace('\x00','')
				else:  # Azure
					if log_type == 'DraftLog':
						initial = file_info['blob_client'].download_blob().readall().decode('utf-8').replace('\r','')
					else:  # GameLog
						initial = file_info['blob_client'].download_blob().readall().decode('utf-8', errors='ignore')
						initial = initial.replace('\x00','')

				# Process based on log type
				if log_type == 'GameLog':
					fname = filename.split('_')[-1].split('.dat')[0]
					
					if Removed.query.filter_by(uid=uid, match_id=fname).first():
						counts['gamelogs_skipped_removed'] += 1
						continue

					try:
						parsed_data = modo.get_all_data(initial,mtime,fname)
						parsed_data_inverted = modo.invert_join([[parsed_data[0]], parsed_data[1], parsed_data[2], parsed_data[3], parsed_data[4]])
						counts['total_gamelogs'] += 1
					except Exception as error:
						counts['gamelogs_skipped_error'] += 1
						if str(error) in game_errors:
							game_errors[str(error)] += 1
						else:
							game_errors[str(error)] = 0
						continue

					if len(parsed_data_inverted[2]) == 0:
						newIgnore = Removed(uid=uid, match_id=fname, reason='Empty')
						db.session.add(newIgnore)
						counts['gamelogs_skipped_empty'] += 1
						continue
				
				elif log_type == 'DraftLog':
					debug_log(f"🔍 DRAFTLOG DEBUG: Processing DraftLog file: {filename}")
					try:
						parsed_data = modo.parse_draft_log(filename, initial)
						debug_log(f"🔍 DRAFTLOG DEBUG: Successfully parsed {filename}")
						debug_log(f"🔍 DRAFTLOG DEBUG: parsed_data[0] (drafts) length: {len(parsed_data[0])}")
						debug_log(f"🔍 DRAFTLOG DEBUG: parsed_data[1] (picks) length: {len(parsed_data[1])}")
						counts['total_draftlogs'] += 1
					except Exception as error:
						debug_log(f"🔍 DRAFTLOG DEBUG: Failed to parse {filename}: {error}")
						counts['draftlogs_skipped_error'] += 1
						if str(error) in draft_errors:
							draft_errors[str(error)] += 1
						else:
							draft_errors[str(error)] = 0
						continue

				# Continue with processing parsed data for both GameLog and DraftLog
				if log_type == 'GameLog':
					# GameLog database operations
					for match in parsed_data_inverted[0]:
						if Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first():
							existing = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
							existing.p2 = match[5]
							existing.p1_roll = match[8]
							existing.p2_roll = match[9]
							existing.roll_winner = match[10]
							existing.date = match[17]
							Play.query.filter_by(uid=uid, match_id=match[0]).delete()
							try:
								db.session.commit()
							except:
								db.session.rollback()
							counts['matches_replaced'] += 1
						else:
							new_match = Match(uid=uid,
											match_id=match[0],
											draft_id=match[1],
											p1=match[2],
											p1_arch=match[3],
											p1_subarch=match[4],
											p2=match[5],
											p2_arch=match[6],
											p2_subarch=match[7],
											p1_roll=match[8],
											p2_roll=match[9],
											roll_winner=match[10],
											p1_wins=match[11],
											p2_wins=match[12],
											match_winner=match[13],
											format=match[14],
											limited_format=match[15],
											match_type=match[16],
											date=match[17])
							db.session.add(new_match)
							counts['new_matches'] += 1
					for game in parsed_data_inverted[1]:
						if Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first():
							existing = Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first()
							existing.p2=game[2]
							existing.pd_selector=game[4]
							existing.pd_choice=game[5]
							existing.on_play=game[6]
							existing.on_draw=game[7]
							existing.p1_mulls=game[8]
							existing.p2_mulls=game[9]
							existing.turns=game[10]
							try:
								db.session.commit()
							except:
								db.session.rollback()
							counts['games_replaced'] += 1
						else:
							new_game = Game(uid=uid,
											match_id=game[0],
											p1=game[1],
											p2=game[2],
											game_num=game[3],
											pd_selector=game[4],
											pd_choice=game[5],
											on_play=game[6],
											on_draw=game[7],
											p1_mulls=game[8],
											p2_mulls=game[9],
											turns=game[10],
											game_winner=game[11])
							db.session.add(new_game)
							counts['new_games'] += 1
					for play in parsed_data_inverted[2]:
						if Play.query.filter_by(uid=uid, match_id=play[0], game_num=play[1], play_num=play[2]).first():
							continue
						new_play = Play(uid=uid,
										match_id=play[0],
										game_num=play[1],
										play_num=play[2],
										turn_num=play[3],
										casting_player=play[4],
										action=play[5],
										primary_card=play[6],
										target1=play[7],
										target2=play[8],
										target3=play[9],
										opp_target=play[10],
										self_target=play[11],
										cards_drawn=play[12],
										attackers=play[13],
										active_player=play[14],
										non_active_player=play[15])
						db.session.add(new_play)
						counts['new_plays'] += 1
					for game in parsed_data_inverted[3]:
						if GameActions.query.filter_by(uid=uid, match_id=game[:-2], game_num=game[-1]).first():
							continue
						new_ga15 = GameActions(uid=uid,
											match_id=game[:-2],
											game_num=game[-1],
											game_actions='\n'.join(parsed_data_inverted[3][game][-15:]))
						db.session.add(new_ga15)
					try:
						db.session.commit()
					except:
						db.session.rollback()
				elif log_type == 'DraftLog':
					# DraftLog database operations
					debug_log(f"🔍 DRAFTLOG DB: Processing DraftLog database operations for {filename}")
					debug_log(f"🔍 DRAFTLOG DB: Number of drafts to process: {len(parsed_data[0])}")
					for draft in parsed_data[0]:
						debug_log(f"🔍 DRAFTLOG DB: Processing draft_id: {draft[0]}, hero: {draft[1]}")
						if Draft.query.filter_by(uid=uid, draft_id=draft[0], hero=draft[1]).first():
							debug_log(f"🔍 DRAFTLOG DB: Draft {draft[0]} already exists, updating...")
							existing = Draft.query.filter_by(uid=uid, draft_id=draft[0], hero=draft[1]).first()
							existing.player2 = draft[2]
							existing.player3 = draft[3]
							existing.player4 = draft[4]
							existing.player5 = draft[5]
							existing.player6 = draft[6]
							existing.player7 = draft[7]
							existing.player8 = draft[8]
							existing.format = draft[11]
							existing.date = draft[12]
							Pick.query.filter_by(uid=uid, draft_id=draft[0]).delete()
							counts['drafts_replaced'] += 1
							try:
								db.session.commit()
							except:
								db.session.rollback()
						else:
							debug_log(f"🔍 DRAFTLOG DB: Creating new draft {draft[0]}")
							new_draft = Draft(uid=uid,
											draft_id=draft[0],
											hero=draft[1],
											player2=draft[2],
											player3=draft[3],
											player4=draft[4],
											player5=draft[5],
											player6=draft[6],
											player7=draft[7],
											player8=draft[8],
											match_wins=draft[9],
											match_losses=draft[10],
											format=draft[11],
											date=draft[12])
							db.session.add(new_draft)
							counts['new_drafts'] += 1
							debug_log(f"🔍 DRAFTLOG DB: Added new draft {draft[0]} to session")
							
					debug_log(f"🔍 DRAFTLOG DB: Number of picks to process: {len(parsed_data[1])}")
					for pick in parsed_data[1]:
						if Pick.query.filter_by(uid=uid, draft_id=pick[0], pick_ovr=pick[4]).first():
							continue
						p = pick
						for index,i in enumerate(p):
							if i == 'NA':
								p[index] = ''
						new_pick = Pick(uid=uid,
										draft_id=pick[0],
										card=pick[1],
										pack_num=pick[2],
										pick_num=pick[3],
										pick_ovr=pick[4],
										avail1=p[5],
										avail2=p[6],
										avail3=p[7],
										avail4=p[8],
										avail5=p[9],
										avail6=p[10],
										avail7=p[11],
										avail8=p[12],
										avail9=p[13],
										avail10=p[14],
										avail11=p[15],
										avail12=p[16],
										avail13=p[17],
										avail14=p[18])
						db.session.add(new_pick)
						counts['new_picks'] += 1
					debug_log(f"🔍 DRAFTLOG DB: Added {counts['new_picks']} picks to session for this file")
					try:
						db.session.commit()
						debug_log(f"🔍 DRAFTLOG DB: Successfully committed {counts['new_drafts']} drafts and {counts['new_picks']} picks to database")
					except Exception as e:
						debug_log(f"🔍 DRAFTLOG DB: Failed to commit to database: {e}")
						db.session.rollback()
				if self.is_aborted():
					return 'TASK STOPPED'
			
			# TaskHistory creation and email operations (MOVED BEFORE build_cards_played_db)
			complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
			curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
			curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')
			
			new_task_history = TaskHistory(
				uid=data['user_id'],
				curr_username=data['username'],
				submit_date=submit_date,
				complete_date=complete_date,
				task_type='Import',
				error_code=error_code
			)
			db.session.add(new_task_history)
			try:
				db.session.commit()
			except:
				db.session.rollback()

			# Email operations (within Flask app context)
			debug_log("📧 LOAD REPORT: Starting email operations...")
			debug_log(f"📧 LOAD REPORT: Recipient email: {data['email']}")
			debug_log(f"📧 LOAD REPORT: Task ID: {new_task_history.task_id}")
			
			mail = app.extensions['mail']
			msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=app.config.get('MAIL_USERNAME'), recipients=[data['email']])
			debug_log("📧 LOAD REPORT: Message object created")
			
			msg.html = f'''
		<h2 style="text-align: center">Load Report, Import GameLogs - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table>
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Records Loaded</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_picks']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Updated</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['matches_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['games_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['plays_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['drafts_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['picks_replaced']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Skipped (Already Loaded)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Gamelogs Skipped (Removed)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Gamelogs Skipped (Empty)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_empty']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
				</tbody>
			</table>	
		</div>
		<div style="display: flex; justify-content: center;">
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.</p>
		</div>
		'''
			debug_log("📧 LOAD REPORT: About to send email...")
			try:
				mail.send(msg)
				debug_log("📧 EMAIL SUCCESS: Load report email sent successfully!")
			except Exception as e:
				debug_log(f"📧 EMAIL ERROR: Failed to send load report email: {e}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_SERVER={app.config.get('MAIL_SERVER')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_USERNAME={app.config.get('MAIL_USERNAME')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_PORT={app.config.get('MAIL_PORT')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_USE_TLS={app.config.get('MAIL_USE_TLS')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_USE_SSL={app.config.get('MAIL_USE_SSL')}")
			
			# Now run build_cards_played_db (after email is sent)
			build_cards_played_db(uid)
	
	except Exception as e:
		error_code = e

	return 'DONE'

@shared_task(bind=True, base=AbortableTask)
def process_from_app(self, data):
	counts = {
		'new_matches':0,
		'new_games':0,
		'new_plays':0,
		'new_drafts':0,
		'new_picks':0,
		'updated_matches':0,
		'updated_games':0,
		'updated_plays':0,
		'updated_drafts':0,
		'updated_picks':0,
		'skipped_plays':0,
		'skipped_drafts':0,
		'skipped_picks':0,
		'gamelogs_skipped_digit':0,
		'gamelogs_skipped_error':0,
		'gamelogs_skipped_removed':0,
		'gamelogs_skipped_empty':0,
		'draftlogs_skipped_error':0,
		'draftlogs_skipped_removed':0,
		'draftlogs_skipped_empty':0,
		'total_gamelogs':0,
		'total_draftlogs':0
	}
	uid = data['user_id']
	new_match_dict = {}
	submit_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	error_code = None

	# Get Flask app from Celery BEFORE processing files
	from app import create_app
	app = create_app()
	debug_log(f'App Created')
	with app.app_context():
		debug_log(f'App Context')
		try:
			debug_log(f'Starting Match Loop')
			debug_log(f'Match Loop Length: {len(data["all_data"][0])}')
			for match in data['all_data'][0]:
				new_match_dict[match[0]] = False
				if match[0][0:12].isdigit():
					debug_log(f'Skipping Match: {match[0]} is digit')
					counts['gamelogs_skipped_digit'] += 1
					continue
				if Removed.query.filter_by(uid=uid, match_id=match[0]).first():
					debug_log(f'Skipping Match: {match[0]} is in removed table')
					counts['gamelogs_skipped_removed'] += 1
					continue
				if Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first():
					debug_log(f'Updating Match: {match[0]} is in match table')
					existing_match = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
					existing_match.p1_arch = match[3]
					existing_match.p1_subarch = match[4]
					existing_match.p2_arch = match[6]
					existing_match.p2_subarch = match[7]
					existing_match.p1_wins = match[11]
					existing_match.p2_wins = match[12]
					existing_match.match_winner = match[13]
					existing_match.format = match[14]
					existing_match.limited_format = match[15]
					existing_match.match_type = match[16]
					merged_match = db.session.merge(existing_match)
					db.session.add(merged_match)
					counts['updated_matches'] += 1
				else:
					debug_log(f'Adding Match: {match[0]} is not in match table')
					new_match = Match(uid=uid,
									match_id=match[0],
									draft_id=match[1],
									p1=match[2],
									p1_arch=match[3],
									p1_subarch=match[4],
									p2=match[5],
									p2_arch=match[6],
									p2_subarch=match[7],
									p1_roll=match[8],
									p2_roll=match[9],
									roll_winner=match[10],
									p1_wins=match[11],
									p2_wins=match[12],
									match_winner=match[13],
									format=match[14],
									limited_format=match[15],
									match_type=match[16],
									date=match[17])
					db.session.add(new_match)
					new_match_dict[match[0]] = True
					counts['new_matches'] += 1
			debug_log(f'Starting Game Loop')
			for game in data['all_data'][1]:
				if game[0][0:12].isdigit():
					continue
				if Removed.query.filter_by(uid=uid, match_id=game[0]).first():
					continue
				if Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first():
					existing_game = Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first()
					existing_game.game_winner = game[11]
					merged_game = db.session.merge(existing_game)
					db.session.add(merged_game)
					counts['updated_games'] += 1
				else:
					new_game = Game(uid=uid,
									match_id=game[0],
									p1=game[1],
									p2=game[2],
									game_num=game[3],
									pd_selector=game[4],
									pd_choice=game[5],
									on_play=game[6],
									on_draw=game[7],
									p1_mulls=game[8],
									p2_mulls=game[9],
									turns=game[10],
									game_winner=game[11])
					db.session.add(new_game)
					counts['new_games'] += 1
			debug_log(f'Starting Play Loop')
			for play in data['all_data'][2]:
				if play[0][0:12].isdigit():
					continue
				if new_match_dict[play[0]] == False:
					continue
				if Removed.query.filter_by(uid=uid, match_id=play[0]).first():
					continue
				if Play.query.filter_by(uid=uid, match_id=play[0], game_num=play[1], play_num=play[2]).first():
					counts['skipped_plays'] += 1
					continue
				else:
					new_play = Play(uid=uid,
									match_id=play[0],
									game_num=play[1],
									play_num=play[2],
									turn_num=play[3],
									casting_player=play[4],
									action=play[5],
									primary_card=play[6],
									target1=play[7],
									target2=play[8],
									target3=play[9],
									opp_target=play[10],
									self_target=play[11],
									cards_drawn=play[12],
									attackers=play[13],
									active_player=play[14],
									non_active_player=play[15])
					db.session.add(new_play)
					counts['new_plays'] += 1
			debug_log(f'Starting Game Action Loop')
			for action in data['all_data'][3]:
				debug_log(f"🔍 DRAFTLOG DB: Processing action: {action[:-2]}")
				if action[0][0:12].isdigit():
					continue
				if new_match_dict[action[:-2]] == False:
					continue
				if Removed.query.filter_by(uid=uid, match_id=action[:-2]).first():
					continue
				if GameActions.query.filter_by(uid=uid, match_id=action[:-2], game_num=action[-1]).first():
					continue
				else:
					new_action = GameActions(uid=uid,
											match_id=action[:-2],
											game_num=action[-1],
											game_actions='\n'.join(data['all_data'][3][action][-15:]))
					db.session.add(new_action)
			debug_log(f'Starting Draft Loop')
			if len(data['drafts_table']) > 0:
				for draft in data['drafts_table']:
					if Removed.query.filter_by(uid=uid, match_id=draft[0]).first():
						continue
					if Draft.query.filter_by(uid=uid, draft_id=draft[0]).first():
						existing_draft = Draft.query.filter_by(uid=uid, draft_id=draft[0]).first()
						existing_draft.hero = draft[1]
						existing_draft.player2 = draft[2]
						existing_draft.player3 = draft[3]
						existing_draft.player4 = draft[4]
						existing_draft.player5 = draft[5]
						existing_draft.player6 = draft[6]
						existing_draft.player7 = draft[7]
						existing_draft.player8 = draft[8]
						existing_draft.match_wins = draft[9]
						existing_draft.match_losses = draft[10]
						existing_draft.format = draft[11]
						existing_draft.date = draft[12]
						merged_draft = db.session.merge(existing_draft)
						db.session.add(merged_draft)
						counts['updated_drafts'] += 1
					else:
						debug_log(f"🔍 DRAFTLOG DB: Creating new draft {draft[0]}")
						new_draft = Draft(uid=uid,
										draft_id=draft[0],
										hero=draft[1],
										player2=draft[2],
										player3=draft[3],
										player4=draft[4],
										player5=draft[5],
										player6=draft[6],
										player7=draft[7],
										player8=draft[8],
										match_wins=draft[9],
										match_losses=draft[10],
										format=draft[11],
										date=draft[12])
						db.session.add(new_draft)
						counts['new_drafts'] += 1
			debug_log(f'Starting Pick Loop')
			for pick in data['picks_table']:
				if Removed.query.filter_by(uid=uid, match_id=pick[0]).first():
					continue
				p = pick
				for index,i in enumerate(p):
					if i == 'NA':
						p[index] = ''
				if Pick.query.filter_by(uid=uid, draft_id=pick[0], pick_ovr=pick[4]).first():
					counts['skipped_picks'] += 1
					continue
				else:
					new_pick = Pick(uid=uid,
									draft_id=pick[0],
									card=pick[1],
									pack_num=pick[2],
									pick_num=pick[3],
									pick_ovr=pick[4],
									avail1=p[5],
									avail2=p[6],
									avail3=p[7],
									avail4=p[8],
									avail5=p[9],
									avail6=p[10],
									avail7=p[11],
									avail8=p[12],
									avail9=p[13],
									avail10=p[14],
									avail11=p[15],
									avail12=p[16],
									avail13=p[17],
									avail14=p[18])
					db.session.add(new_pick)
					counts['new_picks'] += 1
			try:
				debug_log(f'Committing to DB')
				db.session.commit()
			except:
				debug_log(f'DBError: {e}')
				db.session.rollback()
			debug_log(f'counts: {counts}')
			build_cards_played_db(uid)
		except Exception as e:
			debug_log(f'Error: {e}')
			error_code = e

		complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
		curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')

		new_task_history = TaskHistory(
			uid=data['user_id'],
			curr_username=data['username'],
			submit_date=submit_date,
			complete_date=complete_date,
			task_type='Import From MTGO-Tracker',
			error_code=error_code
		)
		db.session.add(new_task_history)
		try:
			db.session.commit()
		except:
			db.session.rollback()

		mail = app.extensions['mail']
		msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=app.config.get('MAIL_USERNAME'), recipients=[data['email']])
		msg.html = f'''
		<h2 style="text-align: center">Load Report, Import from MTGO-Tracker - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table>
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Records Loaded</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_picks']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Updated</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['updated_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['updated_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Outdated*)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_digit']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Ignored)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Duplicate)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['skipped_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['skipped_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['skipped_picks']}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div style="display: flex; justify-content: center;">
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.<br>
			*Outdated records were parsed using an outdated version of MTGO-Tracker.</p>
		</div>
		'''
		mail.send(msg)
		debug_log("📧 DEBUG: Email sent here")

	return 'DONE'

@shared_task(bind=True, base=AbortableTask)
def reprocess_logs(self, data):
	counts = {
		'new_matches':0,
		'new_games':0,
		'new_plays':0,
		'new_drafts':0,
		'new_picks':0,
		'matches_skipped_dupe':0,
		'games_skipped_dupe':0,
		'plays_skipped_dupe':0,
		'drafts_skipped_dupe':0,
		'picks_skipped_dupe':0,
		'gamelogs_skipped_error':0,
		'gamelogs_skipped_removed':0,
		'gamelogs_skipped_empty':0,
		'draftlogs_skipped_error':0,
		'draftlogs_skipped_removed':0,
		'draftlogs_skipped_empty':0,
		'total_gamelogs':0,
		'total_draftlogs':0,
	}
	game_errors = {}
	draft_errors = {}
	uid = data['user_id']
	submit_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	error_code = None

	# Get Flask app from Celery BEFORE processing files
	from app import create_app
	app = create_app()
	
	with app.app_context():
		try:
			# Get list of files to process based on storage type
			files_to_process = []
			
			if log_container_client is None:  # Local file storage
				local_storage_dir = os.path.join('local-dev', 'data', 'uploads', str(uid))
				debug_log(f"🔍 REPROCESS: Looking for files in: {local_storage_dir}")
				debug_log(f"🔍 REPROCESS: Directory exists: {os.path.exists(local_storage_dir)}")
				if os.path.exists(local_storage_dir):
					all_files = os.listdir(local_storage_dir)
					debug_log(f"🔍 REPROCESS: Found {len(all_files)} total files: {all_files}")
					for filename in all_files:
						debug_log(f"🔍 REPROCESS: Processing file: {filename}")
						if filename.endswith('.meta'):  # Skip metadata files
							debug_log(f"🔍 REPROCESS: Skipping {filename} (metadata file)")
							continue
						
						local_file_path = os.path.join(local_storage_dir, filename)
						meta_file_path = local_file_path + '.meta'
						
						# Read metadata
						if os.path.exists(meta_file_path):
							with open(meta_file_path, 'r') as f:
								mtime = f.read().strip()
						else:
							mtime = '202301010000'  # Default fallback
						
						log_type = get_logtype_from_filename(filename)
						debug_log(f"🔍 REPROCESS: File {filename} detected as log_type: '{log_type}'")
						if log_type in ['GameLog', 'DraftLog']:
							debug_log(f"🔍 REPROCESS: Adding {filename} to files_to_process")
							files_to_process.append({
								'filename': filename,
								'path': local_file_path,
								'mtime': mtime,
								'storage_type': 'local',
								'log_type': log_type
							})
						else:
							debug_log(f"🔍 REPROCESS: Skipping {filename} - log_type '{log_type}' not in ['GameLog', 'DraftLog']")
				else:
					debug_log(f"🔍 REPROCESS: Local storage directory does not exist: {local_storage_dir}")
			else:  # Azure Blob Storage
				for blob in log_container_client.list_blobs():
					filename = blob.name.split('/')[-1]
					try:
						blob_uid = blob.name.split('/')[0]
					except:
						blob_uid = 0

					if (get_logtype_from_filename(filename) in ['GameLog', 'DraftLog']) and (str(uid) == blob_uid):
						blob_client = blob_service_client.get_blob_client(container=os.environ.get('LOG_CONTAINER_NAME'), blob=blob.name)
						blob_properties = blob_client.get_blob_properties()
						mtime = blob_properties['metadata']['original_mod_time']
						
						files_to_process.append({
							'filename': filename,
							'blob_client': blob_client,
							'mtime': mtime,
							'storage_type': 'azure',
							'log_type': get_logtype_from_filename(filename)
						})
			
			# Now process all files with unified logic
			debug_log(f"🔍 REPROCESS: Processing {len(files_to_process)} files")

			count_gamelogs = 0
			count_draftlogs = 0
			
			for file_info in files_to_process:
				filename = file_info['filename']
				mtime = file_info['mtime']
				log_type = file_info['log_type']

				debug_log(f'Filename: {filename}, mtime: {mtime}, log_type: {log_type}')
				
				# Read file content based on storage type
				if file_info['storage_type'] == 'local':
					with open(file_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
						initial = f.read().replace('\x00','')
				else:  # Azure
					initial = file_info['blob_client'].download_blob().readall().decode('utf-8', errors='ignore')
					initial = initial.replace('\x00','')

				# Process based on log type
				if log_type == 'GameLog':
					count_gamelogs += 1
					debug_log(f'GameLog: {count_gamelogs}')
					fname = filename.split('_')[-1].split('.dat')[0]

					if Removed.query.filter_by(uid=uid, match_id=fname).first():
						counts['gamelogs_skipped_removed'] += 1
						debug_log(f'Skipping GameLog: {fname} - Removed')
						continue

					try:
						parsed_data = modo.get_all_data(initial,mtime,fname)
						parsed_data_inverted = modo.invert_join([[parsed_data[0]], parsed_data[1], parsed_data[2], parsed_data[3], parsed_data[4]])
						debug_log(f'Parsed Data: {fname}')
						counts['total_gamelogs'] += 1
						if len(parsed_data_inverted) > 3:
							debug_log(f'GameActions: {parsed_data_inverted[3]}')
					except Exception as error:
						counts['gamelogs_skipped_error'] += 1
						if str(error) in game_errors:
							game_errors[str(error)] += 1
						else:
							game_errors[str(error)] = 0
						debug_log(f'Skipping GameLog: {fname} - Error: {error}')
						continue

					if len(parsed_data_inverted[2]) == 0:
						newIgnore = Removed(uid=uid, match_id=fname, reason='Empty')
						db.session.add(newIgnore)
						counts['gamelogs_skipped_empty'] += 1
						debug_log(f'Skipping GameLog: {fname} - Empty')
						continue

					for match in parsed_data_inverted[0]:
						existing = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
						if existing:
							counts['matches_skipped_dupe'] += 1
							continue
						else:
							new_match = Match(uid=uid,
											match_id=match[0],
											draft_id=match[1],
											p1=match[2],
											p1_arch=match[3],
											p1_subarch=match[4],
											p2=match[5],
											p2_arch=match[6],
											p2_subarch=match[7],
											p1_roll=match[8],
											p2_roll=match[9],
											roll_winner=match[10],
											p1_wins=match[11],
											p2_wins=match[12],
											match_winner=match[13],
											format=match[14],
											limited_format=match[15],
											match_type=match[16],
											date=match[17])
							db.session.add(new_match)
							counts['new_matches'] += 1
					for game in parsed_data_inverted[1]:
						existing = Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first()
						if existing:
							counts['games_skipped_dupe'] += 1
							continue
						else:
							new_game = Game(uid=uid,
											match_id=game[0],
											p1=game[1],
											p2=game[2],
											game_num=game[3],
											pd_selector=game[4],
											pd_choice=game[5],
											on_play=game[6],
											on_draw=game[7],
											p1_mulls=game[8],
											p2_mulls=game[9],
											turns=game[10],
											game_winner=game[11])
							db.session.add(new_game)
							counts['new_games'] += 1
					for play in parsed_data_inverted[2]:
						existing = Play.query.filter_by(uid=uid, match_id=play[0], game_num=play[1], play_num=play[2]).first()
						if existing:
							counts['plays_skipped_dupe'] += 1
							continue
						else:
							new_play = Play(uid=uid,
											match_id=play[0],
											game_num=play[1],
											play_num=play[2],
											turn_num=play[3],
											casting_player=play[4],
											action=play[5],
											primary_card=play[6],
											target1=play[7],
											target2=play[8],
											target3=play[9],
											opp_target=play[10],
											self_target=play[11],
											cards_drawn=play[12],
											attackers=play[13],
											active_player=play[14],
											non_active_player=play[15])
							db.session.add(new_play)
							counts['new_plays'] += 1
					for game in parsed_data_inverted[3]:
						if GameActions.query.filter_by(uid=uid, match_id=game[:-2], game_num=game[-1]).first():
							continue
						new_ga15 = GameActions(uid=uid,
											match_id=game[:-2],
											game_num=game[-1],
											game_actions='\n'.join(parsed_data_inverted[3][game][-15:]))
						db.session.add(new_ga15)
					try:
						db.session.commit()
					except:
						db.session.rollback()

				elif log_type == 'DraftLog':
					count_draftlogs += 1
					debug_log(f'DraftLog: {count_draftlogs}')
					fname = filename.split('_')[-1].split('.draftlog')[0]

					if Removed.query.filter_by(uid=uid, match_id=fname).first():
						counts['draftlogs_skipped_removed'] += 1
						continue

					try:
						parsed_data = modo.get_draft_data(initial,mtime,fname)
						counts['total_draftlogs'] += 1
					except Exception as error:
						counts['draftlogs_skipped_error'] += 1
						if str(error) in draft_errors:
							draft_errors[str(error)] += 1
						else:
							draft_errors[str(error)] = 0
						continue

					if len(parsed_data[1]) == 0:
						newIgnore = Removed(uid=uid, match_id=fname, reason='Empty')
						db.session.add(newIgnore)
						counts['draftlogs_skipped_empty'] += 1
						continue

					for draft in [parsed_data[0]]:
						existing = Draft.query.filter_by(uid=uid, draft_id=draft[0]).first()
						if existing:
							counts['drafts_skipped_dupe'] += 1
							continue
						else:
							new_draft = Draft(uid=uid,
											draft_id=draft[0],
											date=draft[1],
											format=draft[2],
											picks=draft[3],
											wins=draft[4],
											losses=draft[5])
							db.session.add(new_draft)
							counts['new_drafts'] += 1

					for pick in parsed_data[1]:
						existing = Pick.query.filter_by(uid=uid, draft_id=pick[0], pick_ovr=pick[4]).first()
						if existing:
							counts['picks_skipped_dupe'] += 1
							continue
						else:
							p = pick
							for index,i in enumerate(p):
								if i == 'NA':
									p[index] = ''
							new_pick = Pick(uid=uid,
											draft_id=pick[0],
											card=pick[1],
											pack_num=pick[2],
											pick_num=pick[3],
											pick_ovr=pick[4],
											avail1=p[5],
											avail2=p[6],
											avail3=p[7],
											avail4=p[8],
											avail5=p[9],
											avail6=p[10],
											avail7=p[11],
											avail8=p[12],
											avail9=p[13],
											avail10=p[14],
											avail11=p[15],
											avail12=p[16],
											avail13=p[17],
											avail14=p[18])
							db.session.add(new_pick)
							counts['new_picks'] += 1
					try:
						db.session.commit()
					except:
						db.session.rollback()
				if self.is_aborted():
					return 'TASK STOPPED'
			build_cards_played_db(uid)
		except Exception as e:
			debug_log(f'Error: {e}')
			error_code = e

		complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
		curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')

		new_task_history = TaskHistory(
			uid=data['user_id'],
			curr_username=data['username'],
			submit_date=submit_date,
			complete_date=complete_date,
			task_type='Re-Process',
			error_code=error_code
		)
		db.session.add(new_task_history)
		try:
			db.session.commit()
		except:
			db.session.rollback()

		mail = app.extensions['mail']
		msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=app.config.get('MAIL_USERNAME'), recipients=[data['email']])
		msg.html = f'''
		<h2 style="text-align: center">Load Report, Re-Processing Data - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table style="text-align: center">
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Reprocessed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['total_gamelogs']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['total_draftlogs']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Matches Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Games Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Plays Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Draft Picks Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_picks']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Removed)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Empty)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_empty']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_empty']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Errors)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_error']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_error']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Skipped (Duplicates)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['matches_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['games_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['plays_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['drafts_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['picks_skipped_dupe']}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div style="display: flex; justify-content: center;">
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.
		</div>
		'''
		mail.send(msg)
		debug_log("📧 DEBUG: Email sent here")

	return 'DONE'

@views.route('/tasks', methods=['GET'])
@login_required
def task_monitor():
	"""Monitor Celery background tasks"""
	try:
		# Get recent task history from database - this is reliable
		recent_tasks = TaskHistory.query.filter_by(uid=current_user.uid).order_by(desc(TaskHistory.submit_date)).limit(10).all()
		
		# For now, skip live Celery monitoring to avoid app context issues
		# Focus on database task history which is most useful
		task_data = {
			'active': {},
			'scheduled': {},
			'reserved': {},
			'recent_history': [task.as_dict() for task in recent_tasks] if recent_tasks else [],
			'info': 'Live task monitoring coming soon. For now, view recent task history below.'
		}
		
		return render_template('task_monitor.html', user=current_user, task_data=task_data)
		
	except Exception as e:
		debug_log(f"Error in task monitor: {e}")
		# Fallback with error message
		task_data = {
			'active': {},
			'scheduled': {},
			'reserved': {},
			'recent_history': [],
			'error': f'Error loading task history: {str(e)}'
		}
		
		return render_template('task_monitor.html', user=current_user, task_data=task_data)

@views.route('/update_vars', methods=['GET'])
@login_required
def update_vars():
	global options, multifaced, all_decks
	if (current_user.uid != 1):
		return 'Forbidden', 403
	try:
		# Force reload by setting to None first
		options = None
		multifaced = None
		all_decks = None
		# Now load fresh data
		ensure_data_loaded()
	except Exception as e:
		flash(f'Error loading auxiliary files: {e}', category='error')
	flash('Loaded all auxiliary files successfully.', category='success')
	return render_template('index.html', user=current_user)

@views.route('/send_confirmation_email', methods=['POST'])
def send_confirmation_email():
	inputs = [request.form.get('confirm_email'), request.form.get('confirm_pwd')]

	if (not inputs[0]) or (not inputs[1]):
		flash(f'Please fill in all fields.', category='error')
		return render_template('login.html', user=current_user, inputs=inputs, not_confirmed=True)

	user = Player.query.filter_by(email=inputs[0]).first()
	if not user:
		flash('Email not found.', category='error')
		return render_template('login.html', user=current_user, inputs=inputs, not_confirmed=True)
	if not check_password_hash(user.pwd, inputs[1]):
		flash('Email/Password combination not found.', category='error')
		return render_template('login.html', user=current_user, inputs=inputs, not_confirmed=True)
	if user.is_confirmed:
		flash('User has already been confirmed.', category='error')
		login_user(user, remember=True)
		return redirect(url_for('views.profile'))
	else:
		token = s.dumps(inputs[0], salt=current_app.config.get("EMAIL_CONFIRMATION_SALT"))
		mail = current_app.extensions['mail'] 
		with current_app.app_context():
			msg = Message('MTGO-Tracker - Email Confirmation', sender=current_app.config.get('MAIL_USERNAME'), recipients=[inputs[0]])
			link = url_for('views.confirm_email', token=token, _external=True)
			msg.body = 'Click the following link to confirm your email:\n\n{}'.format(link)
			mail.send(msg)

		flash(f'New confirmation email has been sent (may need to check spam/junk folder).', category='success')
		return render_template('index.html', user=current_user)

@views.route('/email', methods=['POST'])
def email():
	inputs = [request.form.get('email'), request.form.get('pwd'), request.form.get('pwd_confirm'), request.form.get('hero')]

	if (not inputs[0]) or (not inputs[1]) or (not inputs[2]) or (not inputs[3]):
		flash(f'Please fill in all fields.', category='error')
		return render_template('register.html', user=current_user, inputs=inputs)
	elif inputs[1] != inputs[2]:
		flash(f'Passwords do not match.', category='error')
		return render_template('register.html', user=current_user, inputs=inputs)
	else:
		user = Player.query.filter_by(email=inputs[0]).first()
		if user:
			flash(f'Account with this email address already exists.', category='error')
			return render_template('register.html', user=current_user, inputs=inputs)
		new_user = Player(email=inputs[0], 
						  pwd=generate_password_hash(inputs[1]), 
						  username=inputs[3],
						  created_on=datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')),
						  is_admin=False,
						  is_confirmed=False,
						  confirmed_on=None)
		db.session.add(new_user)
		try:
			db.session.commit()
		except:
			db.session.rollback()

		email = request.form['email']
		token = s.dumps(email, salt=current_app.config.get("EMAIL_CONFIRMATION_SALT"))

		mail = current_app.extensions['mail'] 
		with current_app.app_context():
			msg = Message('MTGO-Tracker - Email Confirmation', sender=current_app.config.get('MAIL_USERNAME'), recipients=[email])
			link = url_for('views.confirm_email', token=token, _external=True)
			msg.body = 'Click the following link to confirm your email:\n\n{}'.format(link)
			mail.send(msg)

		logout_user()
		flash(f'User account created. Email confirmation sent (may need to check spam/junk folder).', category='success')
		return redirect(url_for('views.index'))

@views.route('/reset_pwd', methods=['POST'])
def reset_pwd():
	email = request.form['reset_email']

	if not email:
		flash(f'Please fill in all fields.', category='error')
		return render_template('login.html', user=current_user, inputs=['',''])
	user = Player.query.filter_by(email=email).first()
	if not user:
		flash(f'Account with this email address does not exist.', category='error')
		return render_template('login.html', user=current_user, inputs=['',''])

	token = s.dumps(email, salt=current_app.config.get('RESET_PASSWORD_SALT'))

	mail = current_app.extensions['mail'] 
	with current_app.app_context():
		msg = Message('MTGO-Tracker - Password Reset', sender=current_app.config.get('MAIL_USERNAME'), recipients=[email])
		link = url_for('views.reset_email', token=token, _external=True)
		msg.body = 'Click the following link to reset your password:\n\n{}'.format(link)
		mail.send(msg)

	flash(f'Reset Password email sent (may need to check spam/junk folder).', category='success')
	return render_template('login.html', user=current_user, inputs=[email,""], not_confirmed=False)

@views.route('/confirm_email/<token>')
def confirm_email(token):
	try:
		email = s.loads(token, salt=current_app.config.get('EMAIL_CONFIRMATION_SALT'), max_age=3600)
		user = Player.query.filter_by(email=email).first()
		if user is None:
			return "User not found"
		user.is_confirmed = True
		user.confirmed_on = datetime.datetime.now()
		try:
			db.session.commit()
		except:
			db.session.rollback()
		login_user(user, remember=True)
		flash('Thank you for confirming your email. Welcome to your MTGO-Tracker profile page.', category="success")
		return redirect(url_for('views.profile'))
	except SignatureExpired:
		flash('Email confirmation link has expired.', category='error')
		return redirect(url_for('views.index'))
	except BadTimeSignature:
		flash('The token is not correct.', category='error')
		return redirect(url_for('views.index'))

@views.route('/reset_email/<token>')
def reset_email(token):
	try:
		email = s.loads(token, salt=current_app.config.get('RESET_PASSWORD_SALT'), max_age=3600)
		user = Player.query.filter_by(email=email).first()
		if user is None:
			flash('User not found.', category='error')
			return redirect(url_for('views.index'))
		return render_template('reset_pwd.html', user=current_user, inputs=[email])
	except SignatureExpired:
		flash('Reset Password link has expired.', category='error')
		return redirect(url_for('views.index'))
	except BadTimeSignature:
		flash('The token is not correct.', category='error')
		return redirect(url_for('views.index'))

@views.route('/change_pwd', methods=['POST'])
def change_pwd():
	inputs = [request.form.get('email'), request.form.get('new_pwd'), request.form.get('new_pwd_confirm')]

	user = Player.query.filter_by(email=inputs[0]).first()
	if user is None:
		flash('User not found.', category='error')
		return redirect(url_for('views.index'))
	if (not inputs[0]) or (not inputs[1]) or (not inputs[2]):
		flash(f'Please fill in all fields.', category='error')
		return render_template('reset_pwd.html', user=current_user, inputs=[inputs[1]])
	elif inputs[1] != inputs[2]:
		flash(f'Passwords do not match.', category='error')
		return render_template('reset_pwd.html', user=current_user, inputs=[inputs[1]])
	else:
		user.pwd = generate_password_hash(inputs[1])
		try:
			db.session.commit()
		except:
			db.session.rollback()
		login_user(user, remember=True)
		flash(f'Password updated successfully.', category='success')
		return redirect(url_for('views.profile'))

@views.route('/upload', methods=['POST'])
@login_required
def upload():
	def extract_zip_file(zip_ref, path):
		for member in zip_ref.infolist():
			extracted_file_path = os.path.join(path, member.filename)
			if os.path.exists(extracted_file_path):
				existing_mtime = os.path.getmtime(extracted_file_path)
				new_mtime = time.mktime(member.date_time + (0, 0, -1))
				if new_mtime > existing_mtime:
					continue
			zip_ref.extract(member, path)
			timestamp = time.mktime(member.date_time + (0, 0, -1))
			os.utime(extracted_file_path, (timestamp, timestamp))

	if not os.path.exists('upload'+'\\'+str(1)):
		os.makedirs('upload'+'\\'+str(1))

	uploaded_file = request.files['file']
	temp_location = 'temp.zip'
	uploaded_file.save(temp_location)

	with zipfile.ZipFile(temp_location, 'r') as zip_ref:
		extract_zip_file(zip_ref, 'upload'+'\\'+str(1))
	os.remove(temp_location)

	return 'File uploaded and extracted successfully!'

@views.route('/')
def index():
	return render_template('index.html', user=current_user)

@views.route('/register')
def register():
	if current_user.is_authenticated:
		return redirect(url_for('views.profile'))
	
	inputs = ['', '', '', '']
	return render_template('register.html', user=current_user, inputs=inputs)

@views.route('/login', methods=['GET', 'POST'])
def login():
	if current_user.is_authenticated:
		return redirect(url_for('views.profile'))
	
	if request.method == 'POST':
		login_email = request.form.get('login_email')
		login_pwd = request.form.get('login_pwd')
		user = Player.query.filter_by(email=login_email).first()
		if (not login_email) or (not login_pwd):
			flash(f'Please fill in all fields.', category='error')
			return render_template('login.html', user=current_user, inputs=[login_email, login_pwd])

		if not user:
			flash('Email not found.', category='error')
			return render_template('login.html', user=current_user, inputs=[login_email, login_pwd])

		if check_password_hash(user.pwd, login_pwd):
			if user.is_confirmed == False:
				flash('Email has not been confirmed.', category='error')
				return render_template('login.html', user=current_user, inputs=[login_email, login_pwd], not_confirmed=True)
			login_user(user, remember=True)
			flash('Logged in.', category='success')
			return redirect(url_for('views.profile'))
		else:
			flash('Email/Password combination not found.', category='error')
			return render_template('login.html', user=current_user, inputs=[login_email, login_pwd])

	return render_template('login.html', user=current_user, inputs=['',''])

@views.route('/logout')
@login_required
def logout():
	logout_user()
	flash('User logged out.', category='error')
	return redirect(url_for('views.index'))

@views.route('/load', methods=['POST'])
@login_required
def load():
	if ('file' not in request.files):
		flash('No file uploaded.', category='error')
		return redirect(url_for('views.index'))
	uploaded_file = request.files['file']
	if (uploaded_file.filename == ''):
		flash('No file selected.', category='error')
		return redirect(url_for('views.index'))

	file_stream = io.BytesIO(uploaded_file.read())

	task = process_logs.delay({'email':current_user.email, 'file_stream':file_stream.getvalue(), 'user_id':current_user.uid, 'username':current_user.username})

	flash(f'Your data is now being processed. This may take several minutes depending on the number of files. A Load Report will be emailed upon completion.', category='success')
	return redirect(url_for('views.index'))

@views.route('/load_from_app', methods=['POST'])
@login_required
def load_from_app():
	files = request.files.getlist('folder')
	process_total = 0

	all_data = []
	drafts_table = []
	picks_table = []

	for i in files:
		if not i:
			continue
		filename = i.filename.split('/')[-1]
		debug_log(f'Filename: {filename}')
		if (filename not in ['ALL_DATA', 'DRAFTS_TABLE', 'PICKS_TABLE']):
			continue
		if filename == 'ALL_DATA':
			try:
				all_data = pickle.loads(i.read())
				all_data = modo.invert_join(all_data)
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(all_data[0])
			process_total += len(all_data[1])
			process_total += len(all_data[2])
			process_total += len(all_data[3])
			debug_log(f'All Data: {len(all_data[0])} matches, {len(all_data[1])} games, {len(all_data[2])} plays, {len(all_data[3])} gameactions?')
		elif filename == 'DRAFTS_TABLE':
			try:
				drafts_table = pickle.loads(i.read())
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(drafts_table)
			debug_log(f'Drafts Table: {len(drafts_table)} drafts')
		elif filename == 'PICKS_TABLE':
			try:
				picks_table = pickle.loads(i.read())
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(picks_table)
			debug_log(f'Picks Table: {len(picks_table)} picks')

	if (len(all_data) == 0) and (len(drafts_table) == 0) and (len(picks_table) == 0):
		flash('No MTGO-Tracker save data was found.', 'error')
		return redirect(url_for('views.index'))

	task = process_from_app.delay({'all_data':all_data, 'drafts_table':drafts_table, 'picks_table':picks_table, 'user_id':current_user.uid, 'username':current_user.username, 'email':current_user.email})

	flash(f'MTGO-Tracker save data is being processed. A Load Report will be emailed upon completion.', category='success')
	return redirect(url_for('views.index'))
	
@views.route('/table/<table_name>/<page_num>')
@login_required
def table(table_name, page_num):
	try:
		page_num = int(page_num)
	except ValueError:
		flash(f'ValueError: Probably typed the address incorrectly.', category='error')
		return render_template('tables.html', user=current_user, table_name=table_name)

	if table_name.lower() == 'matches':
		# Uncomment to display fully inverted Matches table.
		#pages = math.ceil(Match.query.filter_by(uid=current_user.uid).count()/page_size)
		pages = math.ceil(Match.query.filter_by(uid=current_user.uid, p1=current_user.username).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		#table = Match.query.filter_by(uid=current_user.uid).order_by(Match.match_id).limit(page_size*int(page_num)).all()
		table = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Match.date)).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'games':
		pages = math.ceil(Game.query.filter_by(uid=current_user.uid, p1=current_user.username).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Game.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Game.match_id), Game.game_num).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'plays':
		pages = math.ceil(Play.query.filter_by(uid=current_user.uid).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Play.query.filter_by(uid=current_user.uid).order_by(desc(Play.match_id), Play.game_num, Play.play_num).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'drafts':
		pages = math.ceil(Draft.query.filter_by(uid=current_user.uid).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Draft.query.filter_by(uid=current_user.uid).order_by(desc(Draft.date)).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'picks':
		pages = math.ceil(Pick.query.filter_by(uid=current_user.uid).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Pick.query.filter_by(uid=current_user.uid).order_by(desc(Pick.draft_id), Pick.pick_ovr).limit(page_size*int(page_num)).all()

	if pages == int(page_num):
		table = table[(int(page_num)-1)*page_size:]
	else:
		table = table[-page_size:]

	page_num = int(page_num)
	if (page_num < 1) or (page_num > pages) or (len(table) == 0):
		flash(f'Either the {table_name.capitalize()} Table is empty or the page number you are trying to view does not exist.', category='error')
		return render_template('tables.html', user=current_user, table_name=table_name, page_num=page_num, pages=pages)  

	return render_template('tables.html', user=current_user, table_name=table_name, table=table, page_num=page_num, pages=pages)

@views.route('/ignored', methods=['GET'])
@login_required
def ignored():
	table = Removed.query.filter_by(uid=current_user.uid).order_by(Removed.match_id).all()
	#table = Removed.query.filter_by(uid=current_user.uid, reason='Ignored').order_by(Removed.match_id).all()
	if len(table) == 0:
		flash(f'No ignored matches to display.', category='error')
		return redirect(url_for('views.profile'))
	return render_template('tables.html', user=current_user, table_name='ignored', table=table)

@views.route('/table/<table_name>/<row_id>/<game_num>')
@login_required
def table_drill(table_name, row_id, game_num):
	if table_name.lower() == 'games':
		table = Game.query.filter_by(uid=current_user.uid, match_id=row_id, p1=current_user.username).order_by(Game.match_id).all() 
	elif table_name.lower() == 'plays':
		table = Play.query.filter_by(uid=current_user.uid, match_id=row_id, game_num=game_num).order_by(Play.match_id).all()  
	elif table_name.lower() == 'picks':
		table = Pick.query.filter_by(uid=current_user.uid, draft_id=row_id).order_by(Pick.pick_ovr).all()  

	return render_template('tables.html', user=current_user, table_name=table_name, table=table)

# New cleaner API routes for Game Winner functionality
@views.route('/api/game-winner/next', methods=['GET'])
@login_required
def api_game_winner_next():
	"""Get the next game that needs a winner assigned"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Query for games with missing winners
		na_query = Game.query.filter_by(
			uid=current_user.uid, 
			game_winner='NA', 
			p1=current_user.username
		).join(
			Match, 
			(Game.uid == Match.uid) & 
			(Game.match_id == Match.match_id) & 
			(Game.p1 == Match.p1)
		).add_entity(Match)

		if na_query.first() is None:
			return jsonify({'hasGames': False})

		# Find first game with game actions
		for game, match in na_query.order_by(asc(Match.date), asc(Game.game_num)).all():
			game_actions_record = GameActions.query.filter_by(
				uid=current_user.uid, 
				match_id=match.match_id, 
				game_num=game.game_num
			).first()
			
			if game_actions_record:
				ga = game_actions_record.game_actions.split('\n')[-15:]
				
				# Format game actions (handle @[...@] formatting)
				formatted_actions = []
				for action in ga:
					if action.count('@[') != action.count('@]'):
						formatted_actions.append(action)
						continue
					
					formatted = action
					for _ in range(action.count('@[')):
						formatted = formatted.replace('@[', '<strong>', 1).replace('@]', '</strong>', 1)
					formatted_actions.append(formatted)
				
				# Prepare response data
				game_data = game.as_dict()
				game_data.update({
					'date': match.date,
					'game_actions': formatted_actions,
					'hasGames': True
				})
				
				return jsonify(game_data)
		
		return jsonify({'hasGames': False})
		
	except Exception as e:
		debug_log(f"Error in api_game_winner_next: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/game-winner/update', methods=['POST'])
@login_required  
def api_game_winner_update():
	"""Update a game winner and return the next game"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_id = data.get('match_id')
		game_num = data.get('game_num')
		winner = data.get('winner')  # 'P1', 'P2', or 'skip'
		p1 = data.get('p1')
		p2 = data.get('p2')
		
		if not all([match_id, game_num, winner]):
			return jsonify({'error': 'Missing required fields'}), 400
		
		# Update game winner if not skipped
		if winner != 'skip':
			games = Game.query.filter_by(
				match_id=match_id, 
				game_num=game_num, 
				uid=current_user.uid
			).all()
			
			matches = Match.query.filter_by(
				match_id=match_id, 
				uid=current_user.uid
			).all()
			
			draft_id = 'NA'
			
			# Determine actual winner name
			if winner == 'P1':
				game_winner = p1
			elif winner == 'P2':
				game_winner = p2
			else:
				game_winner = '0'
			
			# Update games
			for game in games:
				if game.game_winner == 'NA':
					if game.p1 == game_winner:
						game.game_winner = 'P1'
					elif game.p2 == game_winner:
						game.game_winner = 'P2'
			
			# Update matches
			for match in matches:
				draft_id = match.draft_id
				if match.p1 == game_winner:
					match.p1_wins += 1
				elif match.p2 == game_winner:
					match.p2_wins += 1
				
				# Update match winner
				if match.p1_wins > match.p2_wins:
					match.match_winner = 'P1'
				elif match.p2_wins > match.p1_wins:
					match.match_winner = 'P2'
				else:
					match.match_winner = 'NA'
			
			# Delete GameActions records for this game
			GameActions.query.filter_by(
				uid=current_user.uid,
				match_id=match_id,
				game_num=game_num
			).delete()
			
			# Update draft win/loss records
			update_draft_win_loss(
				uid=current_user.uid, 
				username=current_user.username, 
				draft_id=draft_id
			)
			
			try:
				db.session.commit()
			except Exception as e:
				db.session.rollback()
				debug_log(f"Error committing game winner update: {str(e)}")
				return jsonify({'error': 'Failed to update database'}), 500
		
		# Find next game
		current_match_date = Match.query.filter_by(
			match_id=match_id, 
			uid=current_user.uid
		).first().date
		
		rem_games = Game.query.filter_by(
			uid=current_user.uid, 
			game_winner='NA', 
			p1=current_user.username
		).join(
			Match, 
			(Game.uid == Match.uid) & 
			(Game.match_id == Match.match_id) & 
			(Game.p1 == Match.p1)
		).add_entity(Match).filter(
			Match.date >= current_match_date
		).order_by(asc(Match.date), asc(Game.game_num))
		
		# Look for next game after current one
		current_found = False
		for game, match in rem_games.all():
			# Find current game first, then return the next one
			if (match.match_id == match_id) and (game.game_num == int(game_num)):
				current_found = True
				continue
			
			# If we haven't found the current game yet, skip this one
			if not current_found:
				continue
			
			game_actions_record = GameActions.query.filter_by(
				uid=current_user.uid, 
				match_id=match.match_id, 
				game_num=game.game_num
			).first()
			
			if game_actions_record:
				ga = game_actions_record.game_actions.split('\n')[-15:]
				
				# Format game actions
				formatted_actions = []
				for action in ga:
					if action.count('@[') != action.count('@]'):
						formatted_actions.append(action)
						continue
					
					formatted = action
					for _ in range(action.count('@[')):
						formatted = formatted.replace('@[', '<strong>', 1).replace('@]', '</strong>', 1)
					formatted_actions.append(formatted)
				
				# Prepare next game data
				next_game_data = game.as_dict()
				next_game_data.update({
					'date': match.date,
					'game_actions': formatted_actions
				})
				
				return jsonify({
					'hasNextGame': True,
					'nextGame': next_game_data
				})
		
		# No more games found
		return jsonify({'hasNextGame': False})
		
	except Exception as e:
		debug_log(f"Error in api_game_winner_update: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

# New cleaner API routes for Draft ID functionality
@views.route('/api/draft-id/next', methods=['GET'])
@login_required
def api_draft_id_next():
	"""Get the next limited match that needs a draft_id assigned"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	global multifaced
	if multifaced is None:
		try:
			multifaced = get_multifaced_cards()
		except Exception as e:
			debug_log(f"Warning: Could not load multifaced cards: {e}")
			multifaced = {}
	
	def threshold_met(pick_list, played_list):
		if not pick_list or not played_list:
			return 0
		condition_met = sum(1 for i in played_list if i in pick_list)
		perc = (condition_met / len(played_list)) * 100
		return perc
	
	try:
		# Query for limited matches with missing draft_id
		limited_matches = Match.query.filter_by(
			uid=current_user.uid, 
			draft_id='NA', 
			p1=current_user.username
		).filter(
			Match.format.in_(['Cube', 'Booster Draft'])
		).order_by(asc(Match.date))
		
		first_match = limited_matches.first()
		
		# Find a match with valid card data and possible draft associations
		while first_match:
			# Get cards played in this match
			lands = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=first_match.match_id, 
				casting_player=first_match.p1, 
				action='Land Drop'
			).order_by(Play.primary_card)]
			
			nb_lands = [i for i in lands if i not in ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']]
			spells = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=first_match.match_id, 
				casting_player=first_match.p1, 
				action='Casts'
			).order_by(Play.primary_card)]

			# Clean card sets
			nb_lands = list(modo.clean_card_set(set(nb_lands), multifaced))
			lands = list(modo.clean_card_set(set(lands), multifaced))
			spells = list(modo.clean_card_set(set(spells), multifaced))

			# Find possible draft IDs based on card overlap
			draft_ids_100 = []
			draft_ids_80 = []
			draft_ids_all = []

			for draft in Draft.query.filter_by(uid=current_user.uid).filter(
				Draft.date < first_match.date
			).order_by(desc(Draft.date)).all():
				picks = [pick.card for pick in Pick.query.filter_by(
					uid=current_user.uid, 
					draft_id=draft.draft_id
				)]
				picks = list(modo.clean_card_set(set(picks), multifaced))
				pick_perc = threshold_met(pick_list=picks, played_list=(nb_lands + spells))
				
				if pick_perc == 100:
					draft_ids_100.append(draft.draft_id)
				elif pick_perc >= 80:
					draft_ids_80.append(draft.draft_id)
				else:
					draft_ids_all.append(draft.draft_id)
			
			# Prioritize better matches
			possible_draft_ids = []
			if len(draft_ids_100) > 0:
				possible_draft_ids = draft_ids_100
			elif len(draft_ids_80) > 0:
				possible_draft_ids = draft_ids_80
			else:
				possible_draft_ids = draft_ids_all

			if len(possible_draft_ids) > 0:
				# Found a match with possible associations
				match_data = first_match.as_dict()
				match_data.update({
					'lands': sorted(list(set(lands))),
					'spells': sorted(list(set(spells))),
					'possible_draft_ids': possible_draft_ids,
					'hasMatches': True
				})
				
				return jsonify(match_data)

			# Try next match
			limited_matches = limited_matches.filter(Match.date > first_match.date).order_by(Match.date)
			first_match = limited_matches.first()
		
		# No matches found
		return jsonify({'hasMatches': False})
		
	except Exception as e:
		debug_log(f"Error in api_draft_id_next: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/draft-id/update', methods=['POST'])
@login_required  
def api_draft_id_update():
	"""Update a match with draft_id and return the next match"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	global multifaced
	if multifaced is None:
		try:
			multifaced = get_multifaced_cards()
		except Exception as e:
			debug_log(f"Warning: Could not load multifaced cards: {e}")
			multifaced = {}
	
	def threshold_met(pick_list, played_list):
		if not pick_list or not played_list:
			return 0
		condition_met = sum(1 for i in played_list if i in pick_list)
		perc = (condition_met / len(played_list)) * 100
		return perc
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_id = data.get('match_id')
		draft_id = data.get('draft_id')
		skip = data.get('skip', False)
		
		if not match_id:
			return jsonify({'error': 'Missing match_id'}), 400
		
		# Update match with draft_id if not skipped
		if not skip and draft_id:
			matches = Match.query.filter_by(
				uid=current_user.uid, 
				match_id=match_id
			).all()
			
			for match in matches:
				match.draft_id = draft_id
			
			# Update draft match statistics
			match_wins = 0
			match_losses = 0
			associated_matches = Match.query.filter_by(
				uid=current_user.uid, 
				draft_id=draft_id, 
				p1=current_user.username
			)
			
			for match in associated_matches:
				if match.p1_wins > match.p2_wins:
					match_wins += 1
				elif match.p2_wins > match.p1_wins:
					match_losses += 1
			
			draft = Draft.query.filter_by(
				uid=current_user.uid, 
				draft_id=draft_id
			).first()
			
			if draft:
				draft.match_wins = match_wins
				draft.match_losses = match_losses
			
			try:
				db.session.commit()
			except Exception as e:
				db.session.rollback()
				debug_log(f"Error committing draft ID update: {str(e)}")
				return jsonify({'error': 'Failed to update database'}), 500
		
		# Find next match using sequential approach (same as GameWinner)
		current_match_date = Match.query.filter_by(
			match_id=match_id, 
			uid=current_user.uid
		).first().date
		
		# Query for remaining limited matches (include current date for sequential search)
		remaining_matches = Match.query.filter_by(
			uid=current_user.uid, 
			draft_id='NA', 
			p1=current_user.username
		).filter(
			Match.format.in_(['Cube', 'Booster Draft'])
		).filter(
			Match.date >= current_match_date  # Include current date
		).order_by(Match.date)
		
		# Look for next match after current one using sequential logic
		current_found = False
		next_match = None
		for match in remaining_matches.all():
			# Find current match first, then return the next one
			if match.match_id == match_id:
				current_found = True
				continue
			
			# If we haven't found the current match yet, skip this one
			if not current_found:
				continue
			
			# This is the next match after current
			next_match = match
			break
		
		# Find next match with valid card data and possible associations
		while next_match:
			# Get cards played in this match
			lands = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=next_match.match_id, 
				casting_player=next_match.p1, 
				action='Land Drop'
			).order_by(Play.primary_card)]
			
			nb_lands = [i for i in lands if i not in ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']]
			spells = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=next_match.match_id, 
				casting_player=next_match.p1, 
				action='Casts'
			).order_by(Play.primary_card)]

			# Clean card sets
			nb_lands = list(modo.clean_card_set(set(nb_lands), multifaced))
			lands = list(modo.clean_card_set(set(lands), multifaced))
			spells = list(modo.clean_card_set(set(spells), multifaced))

			# Find possible draft IDs based on card overlap
			draft_ids_100 = []
			draft_ids_80 = []
			draft_ids_all = []

			for draft in Draft.query.filter_by(uid=current_user.uid).filter(
				Draft.date < next_match.date
			).order_by(desc(Draft.date)).all():
				picks = [pick.card for pick in Pick.query.filter_by(
					uid=current_user.uid, 
					draft_id=draft.draft_id
				)]
				picks = list(modo.clean_card_set(set(picks), multifaced))
				pick_perc = threshold_met(pick_list=picks, played_list=(nb_lands + spells))
				
				if pick_perc == 100:
					draft_ids_100.append(draft.draft_id)
				elif pick_perc >= 80:
					draft_ids_80.append(draft.draft_id)
				else:
					draft_ids_all.append(draft.draft_id)
			
			# Prioritize better matches
			possible_draft_ids = []
			if len(draft_ids_100) > 0:
				possible_draft_ids = draft_ids_100
			elif len(draft_ids_80) > 0:
				possible_draft_ids = draft_ids_80
			else:
				possible_draft_ids = draft_ids_all

			if len(possible_draft_ids) > 0:
				# Found next match with possible associations
				next_match_data = next_match.as_dict()
				next_match_data.update({
					'lands': sorted(list(set(lands))),
					'spells': sorted(list(set(spells))),
					'possible_draft_ids': possible_draft_ids
				})
				
				return jsonify({
					'hasNextMatch': True,
					'nextMatch': next_match_data
				})

			# Try next match in sequence - continue from where we left off
			current_match_found = False
			temp_next_match = None
			for match in remaining_matches.all():
				if match.match_id == next_match.match_id:
					current_match_found = True
					continue
				if current_match_found:
					temp_next_match = match
					break
			next_match = temp_next_match
		
		# No more matches found
		return jsonify({'hasNextMatch': False})
		
	except Exception as e:
		debug_log(f"Error in api_draft_id_update: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/input_options')
@login_required
def input_options():
	ensure_data_loaded()
	return options

@views.route('/export')
@login_required
def export():
	# Create export directory in local-dev instead of system temp
	export_base_dir = os.path.join('local-dev', 'data', 'excel')
	os.makedirs(export_base_dir, exist_ok=True)
	temp_dir = tempfile.mkdtemp(dir=export_base_dir)
	
	def delayed_cleanup(temp_dir, delay=30):
		"""Clean up temp directory in background after download completes"""
		time.sleep(delay)
		try:
			shutil.rmtree(temp_dir)
			debug_log(f"Background cleanup successful: {temp_dir}")
		except Exception as e:
			debug_log(f"Background cleanup failed: {temp_dir} - {e}")
	
	try:
		file_name = f'{current_user.email}_Tables.zip'
		empty_tables = []
		export_cnt = 0
		created_files = []
		
		# Debug info
		debug_log(f"Export started for user: {current_user.uid}, {current_user.username}")
		
		# Matches
		try:
			query = select(Match).where(
				(Match.uid == current_user.uid) & 
				(Match.p1 == current_user.username)
			)
			matches_df = pd.read_sql(query, db.engine)
			debug_log(f"Matches query returned {len(matches_df)} rows")
			
			if not matches_df.empty:
				matches_df = matches_df.drop('uid', axis=1)
				matches_file = os.path.join(temp_dir, f'{current_user.email}_Matches.xlsx')
				matches_df.to_excel(matches_file, index=False, engine='openpyxl')
				created_files.append(matches_file)
				export_cnt += 1
			else:
				empty_tables.append('Matches')
		except Exception as e:
			debug_log(f"Matches export error: {e}")
			empty_tables.append('Matches')
		
		# Games
		try:
			query = select(Game).where(
				(Game.uid == current_user.uid) & 
				(Game.p1 == current_user.username)
			)
			games_df = pd.read_sql(query, db.engine)
			debug_log(f"Games query returned {len(games_df)} rows")
			
			if not games_df.empty:
				games_df = games_df.drop('uid', axis=1)
				games_file = os.path.join(temp_dir, f'{current_user.email}_Games.xlsx')
				games_df.to_excel(games_file, index=False, engine='openpyxl')
				created_files.append(games_file)
				export_cnt += 1
			else:
				empty_tables.append('Games')
		except Exception as e:
			debug_log(f"Games export error: {e}")
			empty_tables.append('Games')
		
		# Plays
		try:
			query = select(Play).where(Play.uid == current_user.uid)
			plays_df = pd.read_sql(query, db.engine)
			debug_log(f"Plays query returned {len(plays_df)} rows")
			
			if not plays_df.empty:
				plays_df = plays_df.drop('uid', axis=1)
				plays_file = os.path.join(temp_dir, f'{current_user.email}_Plays.xlsx')
				plays_df.to_excel(plays_file, index=False, engine='openpyxl')
				created_files.append(plays_file)
				export_cnt += 1
			else:
				empty_tables.append('Plays')
		except Exception as e:
			debug_log(f"Plays export error: {e}")
			empty_tables.append('Plays')
		
		# Picks
		try:
			query = select(Pick).where(Pick.uid == current_user.uid)
			picks_df = pd.read_sql(query, db.engine)
			debug_log(f"Picks query returned {len(picks_df)} rows")
			
			if not picks_df.empty:
				picks_df = picks_df.drop('uid', axis=1)
				picks_file = os.path.join(temp_dir, f'{current_user.email}_Picks.xlsx')
				picks_df.to_excel(picks_file, index=False, engine='openpyxl')
				created_files.append(picks_file)
				export_cnt += 1
			else:
				empty_tables.append('Picks')
		except Exception as e:
			debug_log(f"Picks export error: {e}")
			empty_tables.append('Picks')
		
		# Drafts
		try:
			query = select(Draft).where(Draft.uid == current_user.uid)
			drafts_df = pd.read_sql(query, db.engine)
			debug_log(f"Drafts query returned {len(drafts_df)} rows")
			
			if not drafts_df.empty:
				drafts_df = drafts_df.drop('uid', axis=1)
				drafts_file = os.path.join(temp_dir, f'{current_user.email}_Drafts.xlsx')
				drafts_df.to_excel(drafts_file, index=False, engine='openpyxl')
				created_files.append(drafts_file)
				export_cnt += 1
			else:
				empty_tables.append('Drafts')
		except Exception as e:
			debug_log(f"Drafts export error: {e}")
			empty_tables.append('Drafts')
		
		# Check if any files were created
		if export_cnt == 0:
			shutil.rmtree(temp_dir)  # Clean up empty temp dir
			debug_log("No data available for export - all tables empty")
			flash('No data available for export.', 'error')
			return redirect(url_for('views.index'))
		
		# Create zip file
		zip_path = os.path.join(temp_dir, file_name)
		with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
			for file_path in created_files:
				# Add file to zip with just the filename (not the full path)
				arcname = os.path.basename(file_path)
				zipf.write(file_path, arcname)
		
		debug_log(f"Export successful - created {export_cnt} files")
		
		# Schedule background cleanup after 30 seconds (plenty of time for download)
		cleanup_thread = threading.Thread(
			target=delayed_cleanup, 
			args=(temp_dir, 30), 
			daemon=True
		)
		cleanup_thread.start()
		debug_log(f"Background cleanup scheduled for: {temp_dir}")
		
		# Send the file directly for download
		return send_file(
			zip_path,
			as_attachment=True,
			download_name=file_name,
			mimetype='application/zip'
		)
		
	except Exception as e:
		# Clean up on error
		try:
			shutil.rmtree(temp_dir)
		except:
			pass
		debug_log(f"Export error: {e}")
		flash(f'Export failed: {str(e)}', 'error')
		return redirect(url_for('views.index'))

@views.route('/best_guess', methods=['POST'])
@login_required
def best_guess():
	# Ensure data is loaded before using global variables
	ensure_data_loaded()
	
	bg_type = request.form.get('BG_Match_Set').strip()
	replace_type = request.form.get('BG_Replace').strip()
	con_count = 0
	lim_count = 0
	all_matches = Match.query.filter_by(uid=current_user.uid)
	debug_log(f"BG_Match_Set: {bg_type}")
	debug_log(f"BG_Replace: {replace_type}")
	if replace_type == 'Overwrite All':
		if (bg_type == 'Limited Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Limited Formats']) )
			for match in matches:
				cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				match.p1_subarch = modo.get_limited_subarch(cards1)
				match.p2_subarch = modo.get_limited_subarch(cards2)
				match.p1_arch = 'Limited'
				match.p2_arch = 'Limited'
				lim_count += 1
		if (bg_type == 'Constructed Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Constructed Formats']) )
			for match in matches:
				yyyy_mm = match.date[0:4] + "-" + match.date[5:7]
				cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				p1_data = modo.closest_list(set(cards1),all_decks,yyyy_mm)
				p2_data = modo.closest_list(set(cards2),all_decks,yyyy_mm)
				match.p1_subarch = p1_data[0]
				match.p2_subarch = p2_data[0]
				con_count += 1

	if replace_type == 'Replace NA':
		all_matches = all_matches.filter( (Match.p1_subarch.in_(['Unknown', 'NA'])) | (Match.p2_subarch.in_(['Unknown', 'NA'])) )
		debug_log(f"All matches: {all_matches.count()}")
		if (bg_type == 'Limited Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Limited Formats']) )
			debug_log(f"Matches1: {matches.count()}")
			for match in matches:
				if match.p1_subarch in ['Unknown', 'NA']:
					cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					match.p1_subarch = modo.get_limited_subarch(cards1)
					match.p1_arch = 'Limited'
					lim_count += 1
				if match.p2_subarch in ['Unknown', 'NA']:
					cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					match.p2_subarch = modo.get_limited_subarch(cards2)
					match.p2_arch = 'Limited'
					lim_count += 1
		if (bg_type == 'Constructed Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Constructed Formats']) )
			debug_log(f"Matches2: {matches.count()}")
			for match in matches:
				yyyy_mm = match.date[0:4] + "-" + match.date[5:7]
				if match.p1_subarch in ['Unknown', 'NA']:
					cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					p1_data = modo.closest_list(set(cards1),all_decks,yyyy_mm)
					match.p1_subarch = p1_data[0]
					con_count += 1
				if match.p2_subarch in ['Unknown', 'NA']:
					cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					p2_data = modo.closest_list(set(cards2),all_decks,yyyy_mm)
					match.p2_subarch = p2_data[0]
					con_count += 1
	try:
		db.session.commit()
	except:
		db.session.rollback()
	return_str = 'Revised deck names for ' + str(con_count) + ' Constructed  Match'
	if con_count != 1:
		return_str += 'es'
	return_str += ' and ' + str(lim_count) + ' Limited Match'
	if lim_count != 1:
		return_str += 'es'
	return_str += '.'
	flash(return_str, category='success')
	return redirect(url_for('views.table', table_name='matches', page_num=1))

@views.route('/profile')
@login_required
def profile():
	def get_max_streak(table,streak_type):
		max_streak = 0
		max_streak_start_date = ''
		max_streak_end_date = 'Current'
		streak = 0
		streak_start_date = ''
		for i in table:
			if (i.match_winner == 'P1') and (streak_type == 'win'):
				streak += 1
			elif (i.match_winner == 'P2') and (streak_type == 'lose'):
				streak += 1
			else:
				if streak == max_streak:
					max_streak_end_date = i.date
				streak = 0
			if streak == 1:
				streak_start_date = i.date
			if streak >= max_streak:
				max_streak = streak
				max_streak_start_date = streak_start_date
				max_streak_end_date = 'Current'
		if max_streak_end_date == 'Current':
			return [max_streak, f'{max_streak_start_date[5:7]}/{max_streak_start_date[8:10]}/{max_streak_start_date[0:4]}', max_streak_end_date]
		else:
			return [max_streak, f'{max_streak_start_date[5:7]}/{max_streak_start_date[8:10]}/{max_streak_start_date[0:4]}', f'{max_streak_end_date[5:7]}/{max_streak_end_date[8:10]}/{max_streak_end_date[0:4]}']
	def get_best_format(table):
		formats = {}
		max_format = 'None'
		max_perc = '0.0%'
		max_float = 0.0
		max_games = 0
		for i in table:
			#debug_log(i)
			if i[0] not in formats.keys():
				formats[i[0]] = [0,0]
			if i[1] == 'P1':
				formats[i[0]][0] = i[2]
			elif i[1] == 'P2':
				formats[i[0]][1] = i[2]
		for i in formats:
			if formats[i][0] == 0:
				formats[i].append(0)
				formats[i].append('0.0%')
			else:
				formats[i].append( formats[i][0]/(formats[i][0]+formats[i][1]) )
				formats[i].append( str(round((formats[i][0]/(formats[i][0]+formats[i][1]))*100,1))+'%' )
				if (formats[i][2] > max_float) and ((formats[i][0] + formats[i][1]) >= 25):
					max_format = i
					max_perc = formats[i][3]
					max_float = formats[i][2]
					max_games = formats[i][0] + formats[i][1]
		return [max_format, max_perc, max_float, max_games]

	table = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(Match.date).all()
	fave_format = db.session.query(Match.format, func.count(Match.uid)).filter(Match.uid == current_user.uid, Match.p1 == current_user.username).group_by(Match.format).order_by(desc(func.count(Match.uid))).first()
	fave_deck = db.session.query(Match.p1_subarch, Match.format, func.count(Match.uid)).filter(Match.uid == current_user.uid, Match.p1 == current_user.username).group_by(Match.p1_subarch, Match.format).order_by(desc(func.count(Match.uid))).first()
	best_format = db.session.query(Match.format, Match.match_winner, func.count(Match.uid)).filter(Match.uid == current_user.uid, Match.p1 == current_user.username).group_by(Match.format, Match.match_winner).all()
	
	longest = Match.query.filter(Match.uid == current_user.uid, Match.p1 == current_user.username)
	longest = longest.join(Game, (Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)).add_entity(Game)

	longest_game = longest.order_by(desc(Game.turns), desc(Match.date)).first()

	stats_dict = {}
	stats_dict['matches_played'] = len(table)
	try:
		stats_dict['fave_format'] = list(fave_format)
	except TypeError:
		stats_dict['fave_format'] = ['None', 0]
	try:
		stats_dict['fave_deck'] = list(fave_deck)
	except TypeError:
		stats_dict['fave_deck'] = ['None', 'NA', 0]
	stats_dict['max_win_streak'] = get_max_streak(table=table,streak_type='win')
	stats_dict['max_lose_streak'] = get_max_streak(table=table,streak_type='lose')
	stats_dict['best_format'] = get_best_format(table=best_format)
	if longest_game:
		stats_dict['longest_game'] = [longest_game[1].turns, longest_game[0].date[5:7]+'/'+longest_game[0].date[8:10]+'/'+longest_game[0].date[0:4], longest_game[0].p1_subarch, longest_game[0].p2_subarch]
	else:
		stats_dict['longest_game'] = [0, 'NA', 'NA', 'NA']

	# Generate match history data for profile page
	def match_result(p1_wins, p2_wins):
		if p1_wins == p2_wins:
			return f'NA {p1_wins}-{p2_wins}'
		elif p1_wins > p2_wins:
			return f'Win {p1_wins}-{p2_wins}'
		elif p2_wins > p1_wins:
			return f'Loss {p1_wins}-{p2_wins}'
	
	def format_match_format(fmt, limited_format):
		if limited_format and limited_format != 'NA':
			return f'{fmt}: {limited_format}'
		return fmt

	def format_date(date_str):
		"""Format date string to 'Month Day, Year' format"""
		if not date_str:
			return str(date_str)

		try:
			date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d-%H:%M').date()
			# Format as "July 6, 2025" (cross-platform compatible)
			formatted_date = date_obj.strftime('%B %d, %Y')
			# Remove leading zero from day if present (e.g., "July 06" -> "July 6")
			return formatted_date.replace(' 0', ' ')
		except ValueError:
			return date_str

	# Get recent match history (last 10 matches)
	match_history_query = Match.query.filter(
		Match.uid == current_user.uid, 
		Match.p1 == current_user.username
	).order_by(desc(Match.date)).limit(10)
	
	match_history_data = match_history_query.all()
	match_history_list = []
	
	for match in match_history_data:
		match_dict = {
			'Date': format_date(match.date),
			'Opponent': match.p2,
			'Deck': match.p1_subarch,
			'Opp_Deck': match.p2_subarch,
			'Match_Result': match_result(match.p1_wins, match.p2_wins),
			'Match_Format': format_match_format(match.format, match.limited_format)
		}
		match_history_list.append(match_dict)

	return render_template('profile.html', user=current_user, stats=stats_dict, match_history=match_history_list)

@views.route('/edit_profile', methods=['POST'])
@login_required
def edit_profile():
	#new_email = request.get_json()['ProfileEmailInputText']
	#new_name = request.get_json()['ProfileNameInputText']
	new_username = request.get_json()['ProfileUsernameInputText'].strip()

	user = Player.query.filter_by(uid=current_user.uid).first()
	#user.email = new_email
	user.username = new_username
	try:
		db.session.commit()
	except:
		db.session.rollback()
	
	return redirect(url_for('views.profile'))

@views.route('/filter_options', methods=['GET'])
@login_required
def filter_options():
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return 'Forbidden', 403
	filter_options_dict = {'Date1':'2000-01-01','Date2':'2999-12-31'}

	table = Match.query.filter_by(uid=current_user.uid, p1=current_user.username)
	plays_table = Play.query.filter_by(uid=current_user.uid, casting_player=current_user.username)

	if (table.count() == 0) or (plays_table.count() == 0):
		return filter_options_dict

	filter_options_dict['Card'] = [i.primary_card for i in plays_table.with_entities(Play.primary_card).distinct().order_by(Play.primary_card).all()]
	filter_options_dict['Card'].remove('NA')
	filter_options_dict['Opponent'] = [i.p2 for i in table.with_entities(Match.p2).distinct().order_by(Match.p2).all()]
	filter_options_dict['Opponent'].sort(key=str.lower)
	filter_options_dict['Format'] = [i.format for i in table.with_entities(Match.format).distinct().order_by(Match.format).all()]
	filter_options_dict['Limited Format'] = [i.limited_format for i in table.with_entities(Match.limited_format).distinct().order_by(Match.limited_format).all()]
	filter_options_dict['Deck'] = [i.p1_subarch for i in table.with_entities(Match.p1_subarch).distinct().order_by(Match.p1_subarch).all()]
	filter_options_dict['Opp. Deck'] = [i.p2_subarch for i in table.with_entities(Match.p2_subarch).distinct().order_by(Match.p2_subarch).all()]
	filter_options_dict['Action'] = ['Land Drop','Casts','Activated Ability','Triggers']
	date1 = Match.query.filter(Match.uid == current_user.uid, Match.p1 == current_user.username).order_by(Match.date.asc()).first().date[0:10].replace('-','')
	filter_options_dict['Date1'] = date1[0:4] + '-' + date1[4:6] + '-' + date1[6:]
	date2 = Match.query.filter(Match.uid == current_user.uid, Match.p1 == current_user.username).order_by(desc(Match.date)).first().date[0:10].replace('-','')
	filter_options_dict['Date2'] = date2[0:4] + '-' + date2[4:6] + '-' + date2[6:]
	return filter_options_dict

@views.route('/getting_started', methods=['GET'])
def getting_started():
	return render_template('getting-started.html', user=current_user)

@views.route('/faq', methods=['GET'])
def faq():
	return render_template('faq.html', user=current_user)

@views.route('/contact', methods=['GET'])
def contact():
	return render_template('contact.html', user=current_user)

@views.route('/changelog', methods=['GET'])
def changelog():
	return render_template('changelog.html', user=current_user)

@views.route('/zip', methods=['GET'])
def zip():
	return send_file(os.path.join(os.getcwd() + '\\website\\static', 'Zip-MTGO-Logs.exe'), as_attachment=True)

@views.route('/reprocess', methods=['POST'])
@login_required
def reprocess():
	task = reprocess_logs.delay({'email':current_user.email, 'user_id':current_user.uid, 'username':current_user.username})

	flash(f'Your data is now being re-processed. This may take several minutes depending on the number of files. A Load Report will be emailed upon completion.', category='success')
	return redirect('/')

@views.route('/data_dictionary', methods=['GET'])
def data_dict():
	return render_template('data-dict.html', user=current_user)

@views.route('/dashboards', methods=['GET'])
@login_required
def dashboards():
	return render_template('dashboards.html', user=current_user)

@views.route('/api/dashboard/filtered-options', methods=['POST'])
@login_required
def api_dashboard_filtered_options():
	"""Get filtered dropdown options based on current filter selections"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Get current filter values
		data = request.get_json()
		current_filters = data.get('filters', {})
		
		# Start with base query for user's matches
		base_query = Match.query.filter_by(uid=current_user.uid, p1=current_user.username)
		
		# Apply current filters EXCEPT card filter (to avoid complex joins for cascading)
		filters_without_card = current_filters.copy()
		card_filter = filters_without_card.pop('card', None)
		
		# Apply non-card filters first
		filtered_matches_query = apply_dashboard_filters(base_query, filters_without_card)
		filtered_matches = filtered_matches_query.all()
		match_ids = [m.match_id for m in filtered_matches]
		
		# If card filter is specified, further filter the matches
		if card_filter and match_ids:
			# Get matches that contain the specified card
			card_match_ids = Play.query.filter(
				Play.uid == current_user.uid,
				Play.casting_player == current_user.username,
				Play.primary_card == card_filter,
				Play.match_id.in_(match_ids)
			).with_entities(Play.match_id).distinct().all()
			
			card_match_ids = [m.match_id for m in card_match_ids]
			filtered_matches = [m for m in filtered_matches if m.match_id in card_match_ids]
			match_ids = card_match_ids
		
		# Get plays data for card filtering options
		plays_query = Play.query.filter(
			Play.uid == current_user.uid,
			Play.casting_player == current_user.username,
			Play.primary_card != 'NA'
		)
		if match_ids:
			plays_query = plays_query.filter(Play.match_id.in_(match_ids))
		plays = plays_query.all()
		
		# Build filtered options
		filtered_options = {}
		
		# Cards (from plays in filtered matches)
		card_options = list(set([play.primary_card for play in plays]))
		card_options.sort()
		filtered_options['Card'] = card_options
		
		# Opponents
		opponent_options = list(set([m.p2 for m in filtered_matches if m.p2]))
		opponent_options.sort(key=str.lower)
		filtered_options['Opponent'] = opponent_options
		
		# Formats
		format_options = list(set([m.format for m in filtered_matches if m.format]))
		format_options.sort()
		filtered_options['Format'] = format_options
		
		# Limited Formats
		limited_format_options = list(set([m.limited_format for m in filtered_matches if m.limited_format]))
		limited_format_options.sort()
		filtered_options['Limited Format'] = limited_format_options
		
		# Decks (p1_subarch)
		deck_options = list(set([m.p1_subarch for m in filtered_matches if m.p1_subarch]))
		deck_options.sort()
		filtered_options['Deck'] = deck_options
		
		# Opponent Decks (p2_subarch)
		opp_deck_options = list(set([m.p2_subarch for m in filtered_matches if m.p2_subarch]))
		opp_deck_options.sort()
		filtered_options['Opp. Deck'] = opp_deck_options
		
		# Date range (from filtered matches)
		if filtered_matches:
			dates = [m.date for m in filtered_matches if m.date]
			if dates:
				dates.sort()
				filtered_options['Date1'] = dates[0][:10]
				filtered_options['Date2'] = dates[-1][:10]
			else:
				filtered_options['Date1'] = '2000-01-01'
				filtered_options['Date2'] = '2999-12-31'
		else:
			filtered_options['Date1'] = '2000-01-01'
			filtered_options['Date2'] = '2999-12-31'
		
		return jsonify(filtered_options)
		
	except Exception as e:
		debug_log(f"Error in api_dashboard_filtered_options: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/dashboard/generate', methods=['POST'])
@login_required
def api_dashboard_generate():
	"""Generate dashboard data based on type and filters"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Get request data
		data = request.get_json()
		dashboard_type = data.get('dashboard_type')
		filters = data.get('filters', {})
		
		if not dashboard_type:
			return jsonify({'error': 'Dashboard type is required'}), 400
		
		# Apply base filters to get user's matches
		base_query = Match.query.filter_by(uid=current_user.uid, p1=current_user.username)
		
		# Apply filters
		filtered_query = apply_dashboard_filters(base_query, filters)
		
		# Generate dashboard data based on type
		dashboard_data = {}
		
		if dashboard_type == 'match-performance':
			dashboard_data = generate_match_performance_dashboard(filtered_query, filters)
		elif dashboard_type == 'card-analysis':
			dashboard_data = generate_card_analysis_dashboard(filtered_query, filters)
		elif dashboard_type == 'opponent-analysis':
			dashboard_data = generate_opponent_analysis_dashboard(filtered_query, filters)
		elif dashboard_type == 'format-breakdown':
			dashboard_data = generate_format_breakdown_dashboard(filtered_query, filters)
		elif dashboard_type == 'deck-performance':
			dashboard_data = generate_deck_performance_dashboard(filtered_query, filters)
		elif dashboard_type == 'time-trends':
			dashboard_data = generate_time_trends_dashboard(filtered_query, filters)
		else:
			return jsonify({'error': 'Invalid dashboard type'}), 400
		
		return jsonify({
			'success': True,
			'dashboard_type': dashboard_type,
			'filters_applied': filters,
			'data': dashboard_data
		})
		
	except Exception as e:
		debug_log(f"Error in api_dashboard_generate: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

def apply_dashboard_filters(query, filters):
	"""Apply filters to the match query"""
	try:
		# Filter by opponent
		if filters.get('opponent'):
			query = query.filter(Match.p2 == filters['opponent'])
		
		# Filter by format
		if filters.get('format'):
			query = query.filter(Match.format == filters['format'])
		
		# Filter by limited format
		if filters.get('limitedFormat'):
			query = query.filter(Match.limited_format == filters['limitedFormat'])
		
		# Filter by deck (p1_subarch)
		if filters.get('deck'):
			query = query.filter(Match.p1_subarch == filters['deck'])
		
		# Filter by opponent deck (p2_subarch)
		if filters.get('oppDeck'):
			query = query.filter(Match.p2_subarch == filters['oppDeck'])
		
		# Filter by date range
		if filters.get('startDate'):
			query = query.filter(Match.date >= filters['startDate'])
		if filters.get('endDate'):
			query = query.filter(Match.date <= filters['endDate'] + '-23:59')
		
		# Filter by card (requires joining with Play table)
		if filters.get('card'):
			query = query.join(Game, (Match.match_id == Game.match_id) & (Match.uid == Game.uid))\
						 .join(Play, (Game.match_id == Play.match_id) & (Game.game_num == Play.game_num) & (Game.uid == Play.uid))\
						 .filter(Play.primary_card == filters['card'])\
						 .filter(Play.casting_player == current_user.username)
		
		return query
		
	except Exception as e:
		debug_log(f"Error applying dashboard filters: {str(e)}")
		raise e

def generate_match_performance_dashboard(filtered_query, filters):
	"""Generate match performance dashboard data"""
	try:
		matches = filtered_query.all()
			
		# Calculate metrics
		total_matches = len(matches)
		wins = len([m for m in matches if m.match_winner == 'P1'])
		die_roll_wins = len([m for m in matches if m.roll_winner == 'P1'])
		losses = total_matches - wins
		win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
		die_roll_wr = (die_roll_wins / total_matches * 100) if total_matches > 0 else 0
		
		# Calculate games statistics
		total_games = sum([m.p1_wins + m.p2_wins for m in matches])
		avg_games_per_match = (total_games / total_matches) if total_matches > 0 else 0
		
		# Performance by Format
		if matches:
			df = pd.DataFrame([{
				'format': m.format,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by format and calculate stats
			format_stats = df.groupby('format').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			format_stats.columns = ['total_matches', 'wins']
			format_stats['losses'] = format_stats['total_matches'] - format_stats['wins']
			format_stats['win_pct'] = (format_stats['wins'] / format_stats['total_matches'] * 100).round(1)
			format_stats = format_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get format as a column
			format_stats = format_stats.reset_index()
			
			# Create table data for the return JSON
			format_performance_table = {
				'title': 'Performance by Format',
				'headers': ['<center>Format</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['format'],
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in format_stats.iterrows()]
			}
		else:
			format_performance_table = {
				'title': 'Performance by Format',
				'headers': ['<center>Format</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': []
			}
		
		# Performance by Match Type
		if matches:
			df = pd.DataFrame([{
				'match_type': m.match_type,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by format and calculate stats
			matchtype_stats = df.groupby('match_type').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			matchtype_stats.columns = ['total_matches', 'wins']
			matchtype_stats['losses'] = matchtype_stats['total_matches'] - matchtype_stats['wins']
			matchtype_stats['win_pct'] = (matchtype_stats['wins'] / matchtype_stats['total_matches'] * 100).round(1)
			matchtype_stats = matchtype_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get format as a column
			matchtype_stats = matchtype_stats.reset_index()
			
			# Create table data for the return JSON
			matchtype_performance_table = {
				'title': 'Performance by Match Type',
				'headers': ['<center>Match Type</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['match_type'],
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in matchtype_stats.iterrows()]
			}
		else:
			matchtype_performance_table = {
				'title': 'Performance by Match Type',
				'headers': ['<center>Match Type</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': []
			}

		# Decks Played
		if matches:
			df = pd.DataFrame([{
				'p1_subarch': m.p1_subarch,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by p1_subarch and calculate stats
			deck_stats = df.groupby('p1_subarch').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			deck_stats.columns = ['total_matches', 'wins']
			deck_stats['losses'] = deck_stats['total_matches'] - deck_stats['wins']
			deck_stats['win_pct'] = (deck_stats['wins'] / deck_stats['total_matches'] * 100).round(1)
			deck_stats['share_pct'] = (deck_stats['total_matches'] / total_matches * 100).round(1)
			deck_stats = deck_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get p1_subarch as a column
			deck_stats = deck_stats.reset_index()
			
			# Create table data for the return JSON
			deck_performance_table = {
				'title': 'Decks Played',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['p1_subarch'],
					f"<center>{row['wins'] + row['losses']} - ({row['share_pct']:.1f}%)</center>",
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in deck_stats.iterrows()]
			}
		else:
			deck_performance_table = {
				'title': 'Decks Played',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': []
			}

		# Observed Metagame
		if matches:
			df = pd.DataFrame([{
				'p2_subarch': m.p2_subarch,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by p2_subarch and calculate stats
			deck_stats = df.groupby('p2_subarch').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			deck_stats.columns = ['total_matches', 'wins']
			deck_stats['losses'] = deck_stats['total_matches'] - deck_stats['wins']
			deck_stats['win_pct'] = (deck_stats['wins'] / deck_stats['total_matches'] * 100).round(1)
			deck_stats['share_pct'] = (deck_stats['total_matches'] / total_matches * 100).round(1)
			deck_stats = deck_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get p2_subarch as a column
			deck_stats = deck_stats.reset_index()
			
			# Create table data for the return JSON
			oppdeck_performance_table = {
				'title': 'Observed Metagame',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['p2_subarch'],
					f"<center>{row['wins'] + row['losses']} - ({row['share_pct']:.1f}%)</center>",
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in deck_stats.iterrows()]
			}
		else:
			oppdeck_performance_table = {
				'title': 'Observed Metagame',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': []
			}
		
		return {
			'metrics': [
				{
					'title': 'Win Rate',
					'value': f'{win_rate:.1f}%',
					'subtitle': f'{wins} wins, {losses} losses',
					'type': 'percentage'
				},
				{
					'title': 'Total Matches',
					'value': str(total_matches),
					'subtitle': 'In selected period',
					'type': 'count'
				},
				{
					'title': 'Die Roll Win Rate',
					'value': f'{die_roll_wr:.1f}%',
					'subtitle': '',
					'type': 'percentage'
				}
			],
			'charts': [
				{
					'title': 'Win Rate Over Time',
					'type': 'line',
					'data': {
						'labels': [],  # TODO: Generate time-based labels
						'datasets': [{
							'label': 'Win Rate',
							'data': []  # TODO: Calculate win rate over time
						}]
					}
				}
			],
			'table_grids': [
				{
					'type': '2x2',
					'title': 'Performance Overview',
					'grid': [
						[format_performance_table, matchtype_performance_table],
						[deck_performance_table, oppdeck_performance_table]
					]
				}
			],
			'tables': [
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating match performance dashboard: {str(e)}")
		raise e

def generate_card_analysis_dashboard(filtered_query, filters):
	"""Generate card analysis dashboard data"""
	try:
		# Get perspective from filters (default to 'hero')
		perspective = filters.get('perspective', 'hero')
		
		# Set up casting player filter based on perspective
		if perspective == 'opponents':
			casting_player_filter = Play.casting_player != current_user.username
			perspective_label = 'Opponents'
		else:
			casting_player_filter = Play.casting_player == current_user.username
			perspective_label = 'Hero'
		
		# Get plays data for these matches (keeping original queries for metrics)
		plays_hero = Play.query.filter(
			Play.uid == current_user.uid,
			Play.casting_player == current_user.username,
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		).all()

		plays_opp = Play.query.filter(
			Play.uid == current_user.uid,
			Play.casting_player != current_user.username,
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		).all()
			
		# Basic card frequency analysis
		card_frequency_hero = {}
		for play in plays_hero:
			card = play.primary_card
			card_frequency_hero[card] = card_frequency_hero.get(card, 0) + 1

		card_frequency_opp = {}
		for play in plays_opp:
			card = play.primary_card
			card_frequency_opp[card] = card_frequency_opp.get(card, 0) + 1
		
		# Sort by frequency
		top_cards_hero = sorted(card_frequency_hero.items(), key=lambda x: x[1], reverse=True)[:10]
		top_cards_opp = sorted(card_frequency_opp.items(), key=lambda x: x[1], reverse=True)[:10]
			
		# Get all games for these matches to calculate game-specific statistics
		games = Game.query.filter(
			Game.uid == current_user.uid,
			Game.p1 == current_user.username
		).all()
		
		# Game 1 Analysis
		games_g1 = [g for g in games if g.game_num == 1]
		total_games_g1 = len(games_g1)
		
		# Get plays for Game 1
		plays_g1 = Play.query.filter(
			Play.uid == current_user.uid,
			casting_player_filter,
			Play.game_num == 1,
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		).all()
		
		# Calculate Game 1 card statistics
		if plays_g1 and total_games_g1 > 0:
			df_g1 = pd.DataFrame([{
				'card': p.primary_card,
				'match_id': p.match_id,
				'game_num': p.game_num
			} for p in plays_g1])
			
			# Count unique games per card (create a composite key)
			df_g1['game_key'] = df_g1['match_id'] + '_' + df_g1['game_num'].astype(str)
			card_games_g1 = df_g1.groupby('card').agg({
				'game_key': 'nunique'
			}).reset_index()
			card_games_g1.columns = ['card', 'games_cast']
			
			# Calculate games cast percentage
			card_games_g1['games_cast_pct'] = (card_games_g1['games_cast'] / total_games_g1 * 100).round(1)

			card_games_g1 = card_games_g1[(card_games_g1['games_cast_pct'] >= 2.5)]
			
			# Calculate game win rate for each card
			card_winrates_g1 = []
			for _, row in card_games_g1.iterrows():
				card = row['card']
				# Find games where this card was cast
				card_plays = [p for p in plays_g1 if p.primary_card == card]
				card_game_keys = set((p.match_id, p.game_num) for p in card_plays)
				
				# Find corresponding games and count wins
				card_games = [g for g in games_g1 if (g.match_id, g.game_num) in card_game_keys]
				wins = len([g for g in card_games if g.game_winner == 'P1'])
				total = len(card_games)
				win_rate = (wins / total * 100) if total > 0 else 0
				card_winrates_g1.append(win_rate)
			
			card_games_g1['game_win_pct'] = card_winrates_g1
			
			# Sort by games cast descending
			card_games_g1 = card_games_g1.sort_values('games_cast', ascending=False)
			
			game1_table = {
				'title': f'Pre-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
				'rows': [[
					row['card'],
					f"<center>{int(row['games_cast'])} - ({row['games_cast_pct']:.1f}%)</center>",
					f"<center>{row['game_win_pct']:.1f}%</center>"
				] for _, row in card_games_g1.iterrows()]
			}
		else:
			game1_table = {
				'title': f'Pre-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
				'rows': []
			}
		
		# Games 2/3 Analysis
		games_g23 = [g for g in games if g.game_num in [2, 3]]
		total_games_g23 = len(games_g23)
		
		# Get plays for Games 2/3
		plays_g23 = Play.query.filter(
			Play.uid == current_user.uid,
			casting_player_filter,
			Play.game_num.in_([2, 3]),
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		).all()
		
		# Calculate Games 2/3 card statistics
		if plays_g23 and total_games_g23 > 0:
			df_g23 = pd.DataFrame([{
				'card': p.primary_card,
				'match_id': p.match_id,
				'game_num': p.game_num
			} for p in plays_g23])
			
			# Count unique games per card (create a composite key)
			df_g23['game_key'] = df_g23['match_id'] + '_' + df_g23['game_num'].astype(str)
			card_games_g23 = df_g23.groupby('card').agg({
				'game_key': 'nunique'
			}).reset_index()
			card_games_g23.columns = ['card', 'games_cast']
			
			# Calculate games cast percentage
			card_games_g23['games_cast_pct'] = (card_games_g23['games_cast'] / total_games_g23 * 100).round(1)

			card_games_g23 = card_games_g23[(card_games_g23['games_cast_pct'] >= 2.5)]
			
			# Calculate game win rate for each card
			card_winrates_g23 = []
			for _, row in card_games_g23.iterrows():
				card = row['card']
				# Find games where this card was cast
				card_plays = [p for p in plays_g23 if p.primary_card == card]
				card_game_keys = set((p.match_id, p.game_num) for p in card_plays)
				
				# Find corresponding games and count wins
				card_games = [g for g in games_g23 if (g.match_id, g.game_num) in card_game_keys]
				wins = len([g for g in card_games if g.game_winner == 'P1'])
				total = len(card_games)
				win_rate = (wins / total * 100) if total > 0 else 0
				card_winrates_g23.append(win_rate)
			
			card_games_g23['game_win_pct'] = card_winrates_g23
			
			# Sort by games cast descending
			card_games_g23 = card_games_g23.sort_values('games_cast', ascending=False)
			
			games23_table = {
				'title': f'Post-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
				'rows': [[
					row['card'],
					f"<center>{int(row['games_cast'])} - ({row['games_cast_pct']:.1f}%)</center>",
					f"<center>{row['game_win_pct']:.1f}%</center>"
				] for _, row in card_games_g23.iterrows()]
			}
		else:
			games23_table = {
				'title': f'Post-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
				'rows': []
			}
		

		return {
			'metrics': [
				{
					'title': 'Unique Cards Played',
					'value': str(len(card_frequency_hero)),
					'subtitle': 'Different cards (non-land)',
					'type': 'count'
				},
				{
					'title': 'Most Played Card',
					'value': top_cards_hero[0][0] if top_cards_hero else 'None',
					'subtitle': f'{top_cards_hero[0][1]} times' if top_cards_hero else 'No data',
					'type': 'text'
				},
				{
					'title': 'Most Played Card Against',
					'value': top_cards_opp[0][0] if top_cards_opp else 'None',
					'subtitle': f'{top_cards_opp[0][1]} times' if top_cards_opp else 'No data',
					'type': 'text'
				}
			],
			'charts': [
				{
					'title': 'Most Played Cards',
					'type': 'bar',
					'data': {
						'labels': [card[0] for card in top_cards_hero],
						'datasets': [{
							'label': 'Times Played',
							'data': [card[1] for card in top_cards_hero]
						}]
					}
				}
			],
			'tables': [
			],
			'table_grids': [
				{
					'type': '2x2',
					'title': 'Performance Overview',
					'grid': [
						[game1_table, games23_table]
					]
				}
			],
		}
		
	except Exception as e:
		debug_log(f"Error generating card analysis dashboard: {str(e)}")
		raise e

def generate_opponent_analysis_dashboard(filtered_query, filters):
	"""Generate opponent analysis dashboard data"""
	try:
		matches = filtered_query.all()
		
		# Basic opponent analysis
		opponent_stats = {}
		for match in matches:
			opp = match.p2
			if opp not in opponent_stats:
				opponent_stats[opp] = {'wins': 0, 'losses': 0, 'total': 0}
			
			opponent_stats[opp]['total'] += 1
			if match.match_winner == 'P1':
				opponent_stats[opp]['wins'] += 1
			else:
				opponent_stats[opp]['losses'] += 1
		
		# Calculate win rates
		for opp in opponent_stats:
			total = opponent_stats[opp]['total']
			wins = opponent_stats[opp]['wins']
			opponent_stats[opp]['win_rate'] = (wins / total * 100) if total > 0 else 0
		
		# Sort by total matches
		top_opponents = sorted(opponent_stats.items(), key=lambda x: x[1]['total'], reverse=True)
		
		return {
			'metrics': [
				{
					'title': 'Unique Opponents',
					'value': str(len(opponent_stats)),
					'subtitle': 'Different players faced',
					'type': 'count'
				},
				{
					'title': 'Most Faced Opponent',
					'value': top_opponents[0][0] if top_opponents else 'None',
					'subtitle': f'{top_opponents[0][1]["total"]} matches' if top_opponents else 'No data',
					'type': 'text'
				},
				{
					'title': 'Best Matchup',
					'value': max(opponent_stats.keys(), key=lambda x: opponent_stats[x]['win_rate']) if opponent_stats else 'None',
					'subtitle': f'{opponent_stats[max(opponent_stats.keys(), key=lambda x: opponent_stats[x]["win_rate"])]["win_rate"]:.1f}% win rate' if opponent_stats else 'No data',
					'type': 'text'
				}
			],
			'charts': [
				{
					'title': 'Win Rate vs Top Opponents',
					'type': 'bar',
					'data': {
						'labels': [opp[0] for opp in top_opponents[:10]],
						'datasets': [{
							'label': 'Win Rate %',
							'data': [opp[1]['win_rate'] for opp in top_opponents[:10]]
						}]
					}
				}
			],
			'tables': [
				{
					'title': 'Opponent Records',
					'headers': ['Opponent', 'Wins', 'Losses', 'Total', 'Win Rate'],
					'rows': [[
						opp[0], 
						str(opp[1]['wins']), 
						str(opp[1]['losses']),
						str(opp[1]['total']),
						f'{opp[1]["win_rate"]:.1f}%'
					] for opp in top_opponents]
				}
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating opponent analysis dashboard: {str(e)}")
		raise e

def generate_format_breakdown_dashboard(filtered_query, filters):
	"""Generate format breakdown dashboard data"""
	try:
		matches = filtered_query.all()
		
		# TODO: Add your custom format analysis here
		# Example calculations you might want to add:
		# - Win rate by format
		# - Most played formats
		# - Performance in limited vs constructed
		# - Format-specific trends over time
		
		# Basic format analysis
		format_stats = {}
		for match in matches:
			fmt = match.format
			if fmt not in format_stats:
				format_stats[fmt] = {'wins': 0, 'losses': 0, 'total': 0}
			
			format_stats[fmt]['total'] += 1
			if match.match_winner == 'P1':
				format_stats[fmt]['wins'] += 1
			else:
				format_stats[fmt]['losses'] += 1
		
		# Calculate win rates
		for fmt in format_stats:
			total = format_stats[fmt]['total']
			wins = format_stats[fmt]['wins']
			format_stats[fmt]['win_rate'] = (wins / total * 100) if total > 0 else 0
		
		return {
			'metrics': [
				{
					'title': 'Formats Played',
					'value': str(len(format_stats)),
					'subtitle': 'Different formats',
					'type': 'count'
				},
				{
					'title': 'Most Played Format',
					'value': max(format_stats.keys(), key=lambda x: format_stats[x]['total']) if format_stats else 'None',
					'subtitle': f'{format_stats[max(format_stats.keys(), key=lambda x: format_stats[x]["total"])]["total"]} matches' if format_stats else 'No data',
					'type': 'text'
				},
				{
					'title': 'Best Format',
					'value': max(format_stats.keys(), key=lambda x: format_stats[x]['win_rate']) if format_stats else 'None',
					'subtitle': f'{format_stats[max(format_stats.keys(), key=lambda x: format_stats[x]["win_rate"])]["win_rate"]:.1f}% win rate' if format_stats else 'No data',
					'type': 'text'
				}
			],
			'charts': [
				{
					'title': 'Matches by Format',
					'type': 'pie',
					'data': {
						'labels': list(format_stats.keys()),
						'datasets': [{
							'data': [stats['total'] for stats in format_stats.values()]
						}]
					}
				}
			],
			'tables': [
				{
					'title': 'Format Performance',
					'headers': ['Format', 'Wins', 'Losses', 'Total', 'Win Rate'],
					'rows': [[
						fmt, 
						str(stats['wins']), 
						str(stats['losses']),
						str(stats['total']),
						f'{stats["win_rate"]:.1f}%'
					] for fmt, stats in format_stats.items()]
				}
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating format breakdown dashboard: {str(e)}")
		raise e

def generate_deck_performance_dashboard(filtered_query, filters):
	"""Generate deck performance dashboard data"""
	try:
		matches = filtered_query.all()
		
		# TODO: Add your custom deck analysis here
		# Example calculations you might want to add:
		# - Win rate by deck archetype
		# - Deck performance over time
		# - Matchup analysis (your deck vs opponent deck)
		# - Meta game analysis
		
		# Basic deck analysis
		deck_stats = {}
		for match in matches:
			deck = match.p1_subarch or 'Unknown'
			if deck not in deck_stats:
				deck_stats[deck] = {'wins': 0, 'losses': 0, 'total': 0}
			
			deck_stats[deck]['total'] += 1
			if match.match_winner == 'P1':
				deck_stats[deck]['wins'] += 1
			else:
				deck_stats[deck]['losses'] += 1
		
		# Calculate win rates
		for deck in deck_stats:
			total = deck_stats[deck]['total']
			wins = deck_stats[deck]['wins']
			deck_stats[deck]['win_rate'] = (wins / total * 100) if total > 0 else 0
		
		return {
			'metrics': [
				{
					'title': 'Decks Played',
					'value': str(len(deck_stats)),
					'subtitle': 'Different deck types',
					'type': 'count'
				},
				{
					'title': 'Most Played Deck',
					'value': max(deck_stats.keys(), key=lambda x: deck_stats[x]['total']) if deck_stats else 'None',
					'subtitle': f'{deck_stats[max(deck_stats.keys(), key=lambda x: deck_stats[x]["total"])]["total"]} matches' if deck_stats else 'No data',
					'type': 'text'
				},
				{
					'title': 'Best Performing Deck',
					'value': max(deck_stats.keys(), key=lambda x: deck_stats[x]['win_rate']) if deck_stats else 'None',
					'subtitle': f'{deck_stats[max(deck_stats.keys(), key=lambda x: deck_stats[x]["win_rate"])]["win_rate"]:.1f}% win rate' if deck_stats else 'No data',
					'type': 'text'
				}
			],
			'charts': [
				{
					'title': 'Win Rate by Deck',
					'type': 'bar',
					'data': {
						'labels': list(deck_stats.keys()),
						'datasets': [{
							'label': 'Win Rate %',
							'data': [stats['win_rate'] for stats in deck_stats.values()]
						}]
					}
				}
			],
			'tables': [
				{
					'title': 'Deck Performance',
					'headers': ['Deck', 'Wins', 'Losses', 'Total', 'Win Rate'],
					'rows': [[
						deck, 
						str(stats['wins']), 
						str(stats['losses']),
						str(stats['total']),
						f'{stats["win_rate"]:.1f}%'
					] for deck, stats in deck_stats.items()]
				}
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating deck performance dashboard: {str(e)}")
		raise e

def generate_time_trends_dashboard(filtered_query, filters):
	"""Generate time trends dashboard data"""
	try:
		matches = filtered_query.order_by(Match.date).all()
		
		# TODO: Add your custom time trend analysis here
		# Example calculations you might want to add:
		# - Win rate over time (daily/weekly/monthly)
		# - Performance trends by season
		# - Activity patterns (matches per day/week)
		# - Format popularity over time
		# - Improvement metrics
		
		# Basic time analysis - group by month
		from collections import defaultdict
		import datetime
		
		monthly_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total': 0})
		
		for match in matches:
			try:
				# Extract year-month from date
				month_key = match.date[:7]  # YYYY-MM format
				monthly_stats[month_key]['total'] += 1
				if match.match_winner == 'P1':
					monthly_stats[month_key]['wins'] += 1
				else:
					monthly_stats[month_key]['losses'] += 1
			except:
				continue
		
		# Calculate win rates
		for month in monthly_stats:
			total = monthly_stats[month]['total']
			wins = monthly_stats[month]['wins']
			monthly_stats[month]['win_rate'] = (wins / total * 100) if total > 0 else 0
		
		# Sort by month
		sorted_months = sorted(monthly_stats.items())
		
		return {
			'metrics': [
				{
					'title': 'Time Period',
					'value': f'{len(sorted_months)} months' if sorted_months else '0 months',
					'subtitle': 'Data available',
					'type': 'text'
				},
				{
					'title': 'Peak Activity Month',
					'value': max(monthly_stats.keys(), key=lambda x: monthly_stats[x]['total']) if monthly_stats else 'None',
					'subtitle': f'{monthly_stats[max(monthly_stats.keys(), key=lambda x: monthly_stats[x]["total"])]["total"]} matches' if monthly_stats else 'No data',
					'type': 'text'
				},
				{
					'title': 'Recent Trend',
					'value': 'Improving' if len(sorted_months) >= 2 and sorted_months[-1][1]['win_rate'] > sorted_months[-2][1]['win_rate'] else 'Stable',
					'subtitle': 'Based on last 2 months',
					'type': 'text'
				}
			],
			'charts': [
				{
					'title': 'Win Rate Over Time',
					'type': 'line',
					'data': {
						'labels': [month[0] for month in sorted_months],
						'datasets': [{
							'label': 'Win Rate %',
							'data': [month[1]['win_rate'] for month in sorted_months]
						}]
					}
				},
				{
					'title': 'Match Activity Over Time',
					'type': 'bar',
					'data': {
						'labels': [month[0] for month in sorted_months],
						'datasets': [{
							'label': 'Matches Played',
							'data': [month[1]['total'] for month in sorted_months]
						}]
					}
				}
			],
			'tables': [
				{
					'title': 'Monthly Performance',
					'headers': ['Month', 'Wins', 'Losses', 'Total', 'Win Rate'],
					'rows': [[
						month[0], 
						str(month[1]['wins']), 
						str(month[1]['losses']),
						str(month[1]['total']),
						f'{month[1]["win_rate"]:.1f}%'
					] for month in sorted_months]
				}
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating time trends dashboard: {str(e)}")
		raise e

# Initialize these variables as None - they'll be loaded on demand
options = None
multifaced = None
all_decks = None

def ensure_data_loaded():
	"""Load global data if not already loaded"""
	global options, multifaced, all_decks
	
	if options is None:
		try:
			options = get_input_options()
		except Exception as e:
			debug_log(f"Warning: Could not load input options: {e}")
			options = {}
			
	if multifaced is None:
		try:
			multifaced = get_multifaced_cards()
		except Exception as e:
			debug_log(f"Warning: Could not load multifaced cards: {e}")
			multifaced = {}
			
	if all_decks is None:
		try:
			all_decks = get_all_decks()
		except Exception as e:
			debug_log(f"Warning: Could not load all decks: {e}")
			all_decks = {}

@views.route('/test_email')
@login_required 
def test_email():
	"""Test email configuration"""
	try:
		from app import create_app
		app = create_app()
		
		with app.app_context():
			debug_log("🔍 Testing email configuration...")
			debug_log(f"📧 MAIL_SERVER: {app.config.get('MAIL_SERVER')}")
			debug_log(f"📧 MAIL_USERNAME: {app.config.get('MAIL_USERNAME')}")
			debug_log(f"📧 MAIL_PORT: {app.config.get('MAIL_PORT')}")
			debug_log(f"📧 MAIL_USE_TLS: {app.config.get('MAIL_USE_TLS')}")
			debug_log(f"📧 MAIL_USE_SSL: {app.config.get('MAIL_USE_SSL')}")
			
			mail = app.extensions['mail']
			msg = Message(
				'MTGO-DB Test Email', 
				sender=app.config.get('MAIL_USERNAME'), 
				recipients=[current_user.email]
			)
			msg.body = 'This is a test email from MTGO-DB to verify email configuration.'
			
			try:
				mail.send(msg)
				debug_log("📧 Test email sent successfully!")
				flash('Test email sent successfully! Check your inbox.', 'success')
			except Exception as e:
				debug_log(f"📧 Test email failed: {e}")
				flash(f'Email test failed: {e}', 'error')
				
	except Exception as e:
		debug_log(f"📧 Email test error: {e}")
		flash(f'Email test error: {e}', 'error')
	
	return redirect(url_for('views.profile'))

@views.route('/view_debug_log')
@login_required
def view_debug_log():
	"""View debug log file"""
	try:
		log_file = os.path.join('local-dev', 'data', 'logs', 'debug_log.txt')
		if os.path.exists(log_file):
			with open(log_file, 'r', encoding='utf-8') as f:
				log_content = f.read()
			return f"<pre>{log_content}</pre>"
		else:
			return "Debug log file not found."
	except Exception as e:
		return f"Error reading debug log: {e}"

# Modern API endpoints for Table functionality
@views.route('/api/table/<table_name>/<int:page_num>')
@login_required
def api_table_data(table_name, page_num):
	"""Get table data with pagination"""
	try:		
		# Determine which table to query
		if table_name.lower() == 'matches':
			total_count = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).count()
			query = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Match.date))
		elif table_name.lower() == 'games':
			total_count = Game.query.filter_by(uid=current_user.uid, p1=current_user.username).count()
			query = Game.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Game.match_id), Game.game_num)
		elif table_name.lower() == 'plays':
			total_count = Play.query.filter_by(uid=current_user.uid).count()
			query = Play.query.filter_by(uid=current_user.uid).order_by(desc(Play.match_id), Play.game_num, Play.play_num)
		elif table_name.lower() == 'drafts':
			total_count = Draft.query.filter_by(uid=current_user.uid).count()
			query = Draft.query.filter_by(uid=current_user.uid).order_by(desc(Draft.date))
		elif table_name.lower() == 'picks':
			total_count = Pick.query.filter_by(uid=current_user.uid).count()
			query = Pick.query.filter_by(uid=current_user.uid).order_by(desc(Pick.draft_id), Pick.pick_ovr)
		else:
			return jsonify({'error': 'Invalid table name'}), 400
		
		# Calculate pagination
		total_pages = math.ceil(total_count / page_size)
		if page_num < 1 or page_num > total_pages:
			return jsonify({'error': 'Invalid page number'}), 400
		
		# Get the data for this page
		offset = (page_num - 1) * page_size
		records = query.offset(offset).limit(page_size).all()
		
		# Convert to JSON-serializable format
		table_data = [record.as_dict() for record in records]
		
		return jsonify({
			'table_name': table_name,
			'page_num': page_num,
			'total_pages': total_pages,
			'total_count': total_count,
			'page_size': page_size,
			'data': table_data,
			'has_previous': page_num > 1,
			'has_next': page_num < total_pages
		})
		
	except Exception as e:
		debug_log(f"Error in api_table_data: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/table/<table_name>/drill/<row_id>/<int:game_num>')
@login_required
def api_table_drill(table_name, row_id, game_num):
	"""Get drill-down table data (filtered child table)"""
	try:
		if table_name.lower() == 'games':
			records = Game.query.filter_by(
				uid=current_user.uid, 
				match_id=row_id, 
				p1=current_user.username
			).order_by(Game.game_num).all()
		elif table_name.lower() == 'plays':
			records = Play.query.filter_by(
				uid=current_user.uid, 
				match_id=row_id, 
				game_num=game_num
			).order_by(Play.play_num).all()
		elif table_name.lower() == 'picks':
			records = Pick.query.filter_by(
				uid=current_user.uid, 
				draft_id=row_id
			).order_by(Pick.pick_ovr).all()
		else:
			return jsonify({'error': 'Invalid drill-down table'}), 400
		
		# Convert to JSON-serializable format
		table_data = [record.as_dict() for record in records]
		
		return jsonify({
			'table_name': table_name,
			'filtered_by': {'row_id': row_id, 'game_num': game_num},
			'data': table_data,
			'total_count': len(table_data)
		})
		
	except Exception as e:
		debug_log(f"Error in api_table_drill: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/match/<match_id>/details')
@login_required
def api_match_details(match_id):
	"""Get detailed match information for revision modal"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Get match data
		match = Match.query.filter_by(
			uid=current_user.uid, 
			match_id=match_id, 
			p1=current_user.username
		).first()
		
		if not match:
			return jsonify({'error': 'Match not found'}), 404
		
		# Get cards played data
		cards = CardsPlayed.query.filter_by(
			uid=current_user.uid, 
			match_id=match_id
		).first()
		
		response_data = match.as_dict()
		
		if cards:
			cards_data = cards.as_dict()
			response_data.update({
				'lands1': cards_data.get('lands1', []),
				'lands2': cards_data.get('lands2', []),
				'plays1': cards_data.get('plays1', []),
				'plays2': cards_data.get('plays2', [])
			})
		
		return jsonify(response_data)
		
	except Exception as e:
		debug_log(f"Error in api_match_details: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/match/revise', methods=['POST'])
@login_required
def api_match_revise():
	"""Revise a single match"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_id = data.get('match_id')
		if not match_id:
			return jsonify({'error': 'Missing match_id'}), 400
		
		# Get the match
		matches = Match.query.filter_by(
			uid=current_user.uid,
			match_id=match_id
		).all()
		
		if not matches:
			return jsonify({'error': 'Match not found'}), 404
		
		# Update match data
		for match in matches:
			if match.p1 == current_user.username:
				if data.get('p1_arch'): match.p1_arch = data['p1_arch']
				if data.get('p1_subarch'): match.p1_subarch = data['p1_subarch']
				if data.get('p2_arch'): match.p2_arch = data['p2_arch']
				if data.get('p2_subarch'): match.p2_subarch = data['p2_subarch']
			else:
				if data.get('p1_arch'): match.p1_arch = data['p2_arch']
				if data.get('p1_subarch'): match.p1_subarch = data['p2_subarch']
				if data.get('p2_arch'): match.p2_arch = data['p1_arch']
				if data.get('p2_subarch'): match.p2_subarch = data['p1_subarch']
			
			if data.get('format'): match.format = data['format']
			if data.get('limited_format'): match.limited_format = data['limited_format']
			if data.get('match_type'): match.match_type = data['match_type']
		
		try:
			db.session.commit()
			return jsonify({'success': True, 'message': 'Match updated successfully'})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing match revision: {str(e)}")
			return jsonify({'error': 'Failed to update match'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_match_revise: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/match/revise-multi', methods=['POST'])
@login_required
def api_match_revise_multi():
	"""Revise multiple matches"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		# Debug logging
		debug_log(f"Multi-revision data received: {data}")
		
		match_ids = data.get('match_ids', [])
		field_to_change = data.get('field_to_change')
		
		if not match_ids or not field_to_change:
			debug_log(f"Missing required fields - match_ids: {match_ids}, field_to_change: {field_to_change}")
			return jsonify({'error': 'Missing required fields'}), 400
		
		# Get the matches
		matches = Match.query.filter(
			Match.match_id.in_(match_ids),
			Match.uid == current_user.uid
		).all()
		
		if not matches:
			return jsonify({'error': 'No matches found'}), 404
		
		# Apply changes based on field type
		for match in matches:
			if field_to_change == 'P1 Deck':
				if match.p1 == current_user.username:
					if match.p1_arch != 'Limited' and data.get('p1_arch'):
						match.p1_arch = data['p1_arch']
					if data.get('p1_subarch'):
						match.p1_subarch = data['p1_subarch']
				else:
					if match.p2_arch != 'Limited' and data.get('p1_arch'):
						match.p2_arch = data['p1_arch']
					if data.get('p1_subarch'):
						match.p2_subarch = data['p1_subarch']
			
			elif field_to_change == 'P2 Deck':
				if match.p1 == current_user.username:
					if match.p2_arch != 'Limited' and data.get('p2_arch'):
						match.p2_arch = data['p2_arch']
					if data.get('p2_subarch'):
						match.p2_subarch = data['p2_subarch']
				else:
					if match.p1_arch != 'Limited' and data.get('p2_arch'):
						match.p1_arch = data['p2_arch']
					if data.get('p2_subarch'):
						match.p1_subarch = data['p2_subarch']
			
			elif field_to_change == 'Format':
				if data.get('format'):
					match.format = data['format']
				if data.get('limited_format'):
					match.limited_format = data['limited_format']
				
				# Handle Limited format archetype changes
				if data.get('format') in options.get('Limited Formats', []):
					match.p1_arch = 'Limited'
					match.p2_arch = 'Limited'
				else:
					if match.p1_arch == 'Limited':
						match.p1_arch = 'NA'
					if match.p2_arch == 'Limited':
						match.p2_arch = 'NA'
			
			elif field_to_change == 'Match Type':
				if data.get('match_type'):
					match.match_type = data['match_type']
		
		try:
			db.session.commit()
			return jsonify({
				'success': True, 
				'message': f'Updated {len(matches)} matches successfully'
			})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing multi-match revision: {str(e)}")
			return jsonify({'error': 'Failed to update matches'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_match_revise_multi: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/match/remove', methods=['POST'])
@login_required
def api_match_remove():
	"""Remove matches (with optional ignore)"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_ids = data.get('match_ids', [])
		remove_type = data.get('remove_type', 'Remove')  # 'Remove' or 'Ignore'
		
		if not match_ids:
			return jsonify({'error': 'No match IDs provided'}), 400
		
		match_count = 0
		game_count = 0
		play_count = 0
		
		for match_id in match_ids:
			# Count records before deletion
			match_count += Match.query.filter_by(uid=current_user.uid, match_id=match_id).count()
			game_count += Game.query.filter_by(uid=current_user.uid, match_id=match_id).count()
			play_count += Play.query.filter_by(uid=current_user.uid, match_id=match_id).count()
			
			# Delete records
			Match.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			Game.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			Play.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			
			# Add to ignored list if requested
			if remove_type == 'Ignore':
				new_ignore = Removed(uid=current_user.uid, match_id=match_id, reason='Ignored')
				db.session.add(new_ignore)
		
		try:
			db.session.commit()
			return jsonify({
				'success': True,
				'message': f'{match_count} Matches removed, {game_count} Games removed, {play_count} Plays removed.',
				'removed_counts': {
					'matches': match_count,
					'games': game_count,
					'plays': play_count
				}
			})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing match removal: {str(e)}")
			return jsonify({'error': 'Failed to remove matches'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_match_remove: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500


@views.route('/api/ignored/remove', methods=['POST'])
@login_required
def api_ignored_remove():
	"""Remove matches from ignored list (unignore them)"""
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_ids = data.get('match_ids', [])
		
		if not match_ids:
			return jsonify({'error': 'No match IDs provided'}), 400
		
		removed_count = 0
		
		for match_id in match_ids:
			# Remove from ignored list
			removed_records = Removed.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			removed_count += removed_records
		
		try:
			db.session.commit()
			return jsonify({
				'success': True,
				'message': f'{removed_count} match(es) removed from ignored list.',
				'removed_count': removed_count
			})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing ignored removal: {str(e)}")
			return jsonify({'error': 'Failed to remove from ignored list'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_ignored_remove: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500
