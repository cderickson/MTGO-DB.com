from flask import render_template, request, Blueprint, flash, redirect, send_file, Response, jsonify, redirect, url_for, current_app, session
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

page_size = 25

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
	url_input = 'https://raw.githubusercontent.com/cderickson/MTGO-Tracker/main/INPUT_OPTIONS.txt'
	in_header = False
	in_instr = True
	input_options = {}
	x = ""
	y = []
	debug_log(os.getcwd())
	with requests.get(url_input) as r:
		initial = r.content.decode('utf-8', errors='ignore')
		initial = initial.replace('\x00','')
		initial = initial.split("\n")
		for i in initial:
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
	return input_options
def get_multifaced_cards():
	url_mfc = 'https://raw.githubusercontent.com/cderickson/MTGO-Tracker/main/MULTIFACED_CARDS.txt'
	multifaced_cards = {}
	with requests.get(url_mfc) as r:
		initial = r.content.decode('utf-8', errors='ignore')
		initial = initial.replace('\x00','')
		initial = initial.split("\n")
		for i in initial:
			if i.isupper():
				multifaced_cards[i] = {}
				last = i
			if ' // ' in i:
				multifaced_cards[last][i.split(' // ')[0]] = i.split(' // ')[1]
	return multifaced_cards
def get_all_decks():
	url_decks = 'https://github.com/cderickson/MTGO-Tracker/blob/main/ALL_DECKS?raw=true'
	with requests.get(url_decks) as r:
		if r.status_code == 200:
			file_content = io.BytesIO(r.content)
			all_decks = pickle.load(file_content)
		else:
			return {}
	return all_decks
def build_cards_played_db(uid):
	debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Building cards played database for user {uid}")
	
	try:
		# Ensure global variables are loaded
		ensure_data_loaded()
		debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Global variables loaded")
		
		query = db.session.query(Match.match_id).filter_by(uid=uid).distinct()
		match_ids = [value[0] for value in query.all()]
		debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Found {len(match_ids)} unique match IDs")
		
		cards_added = 0
		for i in match_ids:
			debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Processing match {i}")
			
			if CardsPlayed.query.filter_by(uid=uid, match_id=i).first():
				debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Match {i} already exists, skipping")
				continue
				
			try:
				players = [value[0] for value in db.session.query(Play.casting_player).filter_by(uid=uid, match_id=i).distinct().all()]
				
				if len(players) < 2:
					debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Match {i} has insufficient players ({len(players)}), skipping")
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
				debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Added cards played for match {i}")
				
			except Exception as e:
				debug_log(f"🔍 BUILD CARDS PLAYED ERROR: Failed to process match {i}: {e}")
				continue
		
		# Single commit at the end for better performance
		if cards_added > 0:
			try:
				db.session.commit()
				debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Successfully committed {cards_added} cards played records")
			except Exception as e:
				debug_log(f"🔍 BUILD CARDS PLAYED ERROR: Failed to commit: {e}")
				db.session.rollback()
		else:
			debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: No new cards played records to add")
			
	except Exception as e:
		debug_log(f"🔍 BUILD CARDS PLAYED CRITICAL ERROR: {e}")
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

	try:
		for match in data['all_data'][0]:
			new_match_dict[match[0]] = False
			if match[0][0:12].isdigit():
				continue
			if Removed.query.filter_by(uid=uid, match_id=match[0]).first():
				counts['gamelogs_skipped_removed'] += 1
				continue
			if Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first():
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
				new_match_dict[match[0]] = True
				new_match = Match(uid=uid,
								match_id=match[0],
								draft_id='NA',
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
		for game in data['all_data'][3]:
			if game[0][0:12].isdigit():
				continue
			if GameActions.query.filter_by(uid=uid, match_id=game[:-2], game_num=game[-1]).first():
				continue
			new_ga15 = GameActions(uid=uid,
								match_id=game[:-2],
								game_num=game[-1],
								game_actions='\n'.join(data['all_data'][3][game]))
			db.session.add(new_ga15)
		
		if (len(data['drafts_table']) > 0) and (len(data['picks_table']) > 0):
			for draft in data['drafts_table']:
				if Removed.query.filter_by(uid=uid, match_id=draft[0]).first():
					counts['draftlogs_skipped_removed'] += 1
					continue
				if Draft.query.filter_by(uid=uid, draft_id=draft[0], hero=draft[1]).first():
					counts['skipped_drafts'] += 1
				else:
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
			db.session.commit()
		except:
			db.session.rollback()
		build_cards_played_db(uid)
	except Exception as e:
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

	mail = current_app.extensions['mail'] 
	with current_app.app_context():
		msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=current_app.config.get('MAIL_USERNAME'), recipients=[data['email']])
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
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.</p>
		</div>
		'''
		# mail.send(msg)  # Temporarily disabled to focus on file processing issue
		debug_log("📧 DEBUG: Email would be sent here (temporarily disabled)")

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

	try:
		for blob in log_container_client.list_blobs():
			filename = blob.name.split('/')[-1]
			try:
				blob_uid = blob.name.split('/')[0]
			except:
				blob_uid = 0

			if (get_logtype_from_filename(filename) == 'GameLog') and (str(uid) == blob_uid):
				blob_client = blob_service_client.get_blob_client(container=os.environ.get('LOG_CONTAINER_NAME'), blob=blob.name)
				blob_properties = blob_client.get_blob_properties()

				initial = blob_client.download_blob().readall().decode('utf-8', errors='ignore')
				initial = initial.replace('\x00','')

				fname = filename.split('_')[-1].split('.dat')[0]
				mtime = blob_properties['metadata']['original_mod_time']

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

				for match in parsed_data_inverted[0]:
					existing = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
					if existing:
						existing.p2 = match[5]
						existing.p1_roll = match[8]
						existing.p2_roll = match[9]
						existing.roll_winner = match[10]
						existing.date = match[17]
						counts['matches_skipped_dupe'] += 1
						Play.query.filter_by(uid=uid, match_id=fname).delete()
						try:
							db.session.commit()
						except:
							db.session.rollback()
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
						existing.p2=game[2]
						existing.pd_selector=game[4]
						existing.pd_choice=game[5]
						existing.on_play=game[6]
						existing.on_draw=game[7]
						existing.p1_mulls=game[8]
						existing.p2_mulls=game[9]
						existing.turns=game[10]
						counts['games_skipped_dupe'] += 1
						try:
							db.session.commit()
						except:
							db.session.rollback()
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
					existing = GameActions.query.filter_by(uid=uid, match_id=game[:-2], game_num=game[-1]).first()
					if existing:
						existing.game_actions = '\n'.join(parsed_data_inverted[3][game][-15:])
					else:
						new_ga15 = GameActions(uid=uid,
											match_id=game[:-2],
											game_num=game[-1],
											game_actions='\n'.join(parsed_data_inverted[3][game][-15:]))
						db.session.add(new_ga15)
				try:
					db.session.commit()
				except:
					db.session.rollback()
			
			if (get_logtype_from_filename(filename) == 'DraftLog') and (str(uid) == blob_uid):
				blob_client = blob_service_client.get_blob_client(container=os.environ.get('LOG_CONTAINER_NAME'), blob=blob.name)
				initial = blob_client.download_blob().readall().decode('utf-8').replace('\r','')

				try:
					parsed_data = modo.parse_draft_log(filename,initial)
					counts['total_draftlogs'] += 1
				except Exception as error:
					counts['draftlogs_skipped_error'] += 1
					if str(error) in draft_errors:
						draft_errors[str(error)] += 1
					else:
						draft_errors[str(error)] = 0
					continue

				for draft in parsed_data[0]:
					existing = Draft.query.filter_by(uid=uid, draft_id=draft[0], hero=draft[1]).first()
					if existing:
						counts['drafts_skipped_dupe'] += 1
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
						try:
							db.session.commit()
						except:
							db.session.rollback()
					else:
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
		error_code = e

	complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
	curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')

	new_task_history = TaskHistory(
		uid=data['user_id'],
		curr_username=data['username'],
		submit_date=submit_date,
		complete_date=complete_date,
		task_type='Reprocess',
		error_code=error_code
	)
	db.session.add(new_task_history)
	try:
		db.session.commit()
	except:
		db.session.rollback()

	mail = current_app.extensions['mail'] 
	with current_app.app_context():
		msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=current_app.config.get('MAIL_USERNAME'), recipients=[data['email']])
		msg.html = f'''
		<h2 style="text-align: center">Load Report, Reprocessing Data - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table style="text-align: center">
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 250px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 250px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Reprocessed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['total_gamelogs']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['total_draftlogs']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 250px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Matches Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 250px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Error)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_error']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_error']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>	
					<tr>
						<th style="font-size: 14pt; max-width: 250px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Ignored)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 250px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Empty)</th>
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
		# mail.send(msg)  # Temporarily disabled to focus on file processing issue
		debug_log("📧 DEBUG: Email would be sent here (temporarily disabled)")

	return 'DONE'

@views.route('/test', methods=['GET'])
def test():
	#return json.dumps(multifaced)
	new_dict = {'1':db.session}
	return json.dumps(new_dict)

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
		elif filename == 'DRAFTS_TABLE':
			try:
				drafts_table = pickle.loads(i.read())
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(drafts_table)
		elif filename == 'PICKS_TABLE':
			try:
				picks_table = pickle.loads(i.read())
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(picks_table)

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

@views.route('/ignored', methods=['POST'])
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

@views.route('/revise', methods=['POST'])
@login_required
def revise():
	match_id = request.form.get('Match_ID')
	p1_arch = request.form.get('P1Arch')
	p1_subarch = request.form.get('P1_Subarch')
	p2_arch = request.form.get('P2Arch')
	p2_subarch = request.form.get('P2_Subarch')
	fmt = request.form.get('Format')
	limited_format = request.form.get('Limited_Format')
	match_type = request.form.get('Match_Type')
	page_num = request.form.get('Page_Num')

	matches = Match.query.filter_by(match_id=match_id).all()
	for match in matches:
		if match.p1 == current_user.username:
			match.p1_arch = p1_arch
			match.p1_subarch = p1_subarch
			match.p2_arch = p2_arch
			match.p2_subarch = p2_subarch
		else:
			match.p1_arch = p2_arch 
			match.p1_subarch = p2_subarch 
			match.p2_arch = p1_arch
			match.p2_subarch = p1_subarch
		match.format = fmt 
		match.limited_format = limited_format
		match.match_type = match_type
	try:
		db.session.commit()
	except:
		db.session.rollback()
	return redirect(url_for('views.table', table_name='matches', page_num=page_num))

@views.route('/revise_multi', methods=['POST'])
@login_required
def revise_multi():
	match_id_str = request.form.get('Match_ID_Multi')
	field_to_change = request.form.get('FieldToChangeMulti')
	p1_arch = request.form.get('P1ArchMulti')
	p1_subarch = request.form.get('P1_Subarch_Multi')
	p2_arch = request.form.get('P2ArchMulti')
	p2_subarch = request.form.get('P2_Subarch_Multi')
	fmt = request.form.get('FormatMulti')
	limited_format = request.form.get('Limited_FormatMulti')
	match_type = request.form.get('Match_TypeMulti')
	page_num = request.form.get('Page_Num_Multi')

	match_ids = match_id_str.split(',')

	matches = Match.query.filter(Match.match_id.in_(match_ids), Match.uid == current_user.uid).all()
	for match in matches:
		if field_to_change == 'P1 Deck':
			if match.p1 == current_user.username:
				if match.p1_arch != 'Limited':
					match.p1_arch = p1_arch
				match.p1_subarch = p1_subarch
			else:
				if match.p2_arch != 'Limited':
					match.p2_arch = p1_arch 
				match.p2_subarch = p1_subarch 
		elif field_to_change == 'P2 Deck':
			if match.p1 == current_user.username:
				if match.p2_arch != 'Limited':
					match.p2_arch = p2_arch
				match.p2_subarch = p2_subarch
			else:
				if match.p1_arch != 'Limited':
					match.p1_arch = p2_arch 
				match.p1_subarch = p2_subarch
		elif field_to_change == 'Format':
			match.format = fmt 
			match.limited_format = limited_format
			if fmt in options['Limited Formats']:
				match.p1_arch = 'Limited'
				match.p2_arch = 'Limited'
			else:
				if match.p1_arch == 'Limited':
					match.p1_arch = 'NA'
				if match.p2_arch == 'Limited':
					match.p2_arch = 'NA'
		elif field_to_change == 'Match Type':
			match.match_type = match_type
	try:
		db.session.commit()
	except:
		db.session.rollback()
	return redirect(url_for('views.table', table_name='matches', page_num=page_num))

@views.route('/revise_ignored', methods=['POST'])
@login_required
def revise_ignored():
	match_id_str = request.form.get('Ignored_Match_ID_Multi')
	match_ids = match_id_str.split(',')
	for i in match_ids:
		Removed.query.filter_by(uid=current_user.uid, match_id=i).delete()
	try:
		db.session.commit()
	except:
		db.session.rollback()
	table = Removed.query.filter_by(uid=current_user.uid, reason='Ignored').order_by(Removed.match_id).all()
	if len(table) == 0:
		flash(f'No ignored matches to display.', category='error')
		return redirect(url_for('views.profile'))
	return render_template('tables.html', user=current_user, table_name='ignored', table=table)

@views.route('/values/<match_id>', methods=['GET'])
@login_required
def values(match_id):
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return 'Forbidden', 403
	if not current_user.is_authenticated:
		return 'Forbidden', 403
	match = Match.query.filter_by(uid=current_user.uid, match_id=match_id, p1=current_user.username).first().as_dict()
	cards = CardsPlayed.query.filter_by(uid=current_user.uid, match_id=match_id).first().as_dict()
	cards['lands1'] = '<br>'.join(cards['lands1'])
	cards['lands2'] = '<br>'.join(cards['lands2'])
	cards['plays1'] = '<br>'.join(cards['plays1'])
	cards['plays2'] = '<br>'.join(cards['plays2'])
	return match | cards

@views.route('/game_winner/<match_id>/<game_num>/<game_winner>', methods=['GET'])
@login_required
def game_winner(match_id, game_num, game_winner):
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return 'Forbidden', 403
	if not current_user.is_authenticated:
		return 'Forbidden', 403
	if game_winner != '0':
		games = Game.query.filter_by(match_id=match_id, game_num=game_num, uid=current_user.uid).all()
		matches = Match.query.filter_by(match_id=match_id, uid=current_user.uid).all()
		draft_id = 'NA'

		for game in games:
			if game.game_winner != 'NA':
				pass
			if game.p1 == game_winner:
				game.game_winner = 'P1'
			elif game.p2 == game_winner:
				game.game_winner = 'P2'
			else:
				pass
		for match in matches:
			draft_id = match.draft_id
			if match.p1 == game_winner:
				match.p1_wins += 1
			elif match.p2 == game_winner:
				match.p2_wins += 1
			else:
				pass
			if match.p1_wins > match.p2_wins:
				match.match_winner = 'P1'
			elif match.p2_wins > match.p1_wins:
				match.match_winner = 'P2'
			elif match.p1_wins == match.p2_wins:
				match.match_winner = 'NA'
			else:
				pass
		update_draft_win_loss(uid=current_user.uid, username=current_user.username, draft_id=draft_id)
		try:
			db.session.commit()
		except:
			db.session.rollback()

	date = Match.query.filter_by(match_id=match_id, uid=current_user.uid).first().date
	rem_games = Game.query.filter_by(uid=current_user.uid, game_winner='NA', p1=current_user.username).join(Match, (Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)).add_entity(Match)
	rem_games = rem_games.filter(Match.date >= date).order_by(asc(Match.date), asc(Game.game_num))
	next_game = None
	if rem_games.first() is None:
		return {'match_id':'NA'}
		#na_count = Game.query.filter_by(uid=current_user.uid, game_winner='NA', p1=current_user.username).count()
		# if na_count == 0:
		# 	return {'match_id':'Empty'}
		# else:
		# 	return {'match_id':'NA'}
	else:
		for game,match in rem_games.all():
			if (match.match_id == match_id) and (game.game_num <= int(game_num)):
				continue
			if GameActions.query.filter_by(uid=current_user.uid, match_id=match.match_id, game_num=game.game_num).first():
				next_game = game
				date_dict = {'date':match.date}
				ga = GameActions.query.filter_by(uid=current_user.uid, match_id=match.match_id, game_num=game.game_num).first().game_actions.split('\n')[-15:]
				break
		if not next_game:
			return {'match_id':'NA'}
			#na_count = Game.query.filter_by(uid=current_user.uid, game_winner='NA', p1=current_user.username).count()
			# if na_count == 0:
			# 	return {'match_id':'Empty'}
			# else:
			# 	return {'match_id':'NA'}

	for index,i in enumerate(ga):
		string = i
		if i.count('@[') != i.count('@]'):
			continue
		for j in range(i.count('@[')):
			string = string.replace('@[','<b>',1).replace('@]','</b>',1)
		ga[index] = string
	ga_dict = {'game_actions' : ga}
	return next_game.as_dict() | ga_dict | date_dict

@views.route('/game_winner_init', methods=['GET'])
def game_winner_init():
	if not current_user.is_authenticated:
		return {'match_id':'NA'}
	na_query = Game.query.filter_by(uid=current_user.uid, game_winner='NA', p1=current_user.username).join(Match, (Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)).add_entity(Match)

	if na_query.first() is None:
		return {'match_id':'NA'}
	else:
		for game,match in na_query.order_by(asc(Match.date), asc(Game.game_num)).all():
			if GameActions.query.filter_by(uid=current_user.uid, match_id=match.match_id, game_num=game.game_num).first():
				first_game = game
				date_dict = {'date':match.date}
				ga = GameActions.query.filter_by(uid=current_user.uid, match_id=match.match_id, game_num=game.game_num).first().game_actions.split('\n')[-15:]
				break
			return {'match_id':'NA'}
	
	for index,i in enumerate(ga):
		string = i
		if i.count('@[') != i.count('@]'):
			continue
		for j in range(i.count('@[')):
			string = string.replace('@[','<b>',1).replace('@]','</b>',1)
		ga[index] = string
	ga_dict = {'game_actions' : ga}
	return first_game.as_dict() | ga_dict | date_dict
	
@views.route('/draft_id_init', methods=['GET'])
def draft_id_init():
	def threshold_met(pick_list, played_list):
		condition_met = sum(1 for i in played_list if i in pick_list)
		perc = (condition_met / len(played_list)) * 100
		return perc
	
	if not current_user.is_authenticated:
		return {'match_id':'NA'}
	
	limited_matches = Match.query.filter_by(uid=current_user.uid, draft_id='NA', p1=current_user.username)
	limited_matches = limited_matches.filter( Match.format.in_(['Cube', 'Booster Draft']) ).order_by(asc(Match.date))
	first_match = limited_matches.first()
	while True:
		if first_match is None:
			return 'Forbidden', 403

		lands = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																	match_id=first_match.match_id, 
																	casting_player=first_match.p1, 
																	action='Land Drop').order_by(Play.primary_card)]
		nb_lands = [i for i in lands if (i not in ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest'])]
		spells = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																	match_id=first_match.match_id, 
																	casting_player=first_match.p1, 
																	action='Casts').order_by(Play.primary_card)]

		nb_lands = list(modo.clean_card_set(set(nb_lands), multifaced))
		lands = list(modo.clean_card_set(set(lands), multifaced))
		spells = list(modo.clean_card_set(set(spells), multifaced))

		cards_dict = {'lands':[*set(lands)], 'spells':[*set(spells)]}
		draft_ids_dict = {'possible_draft_ids':[]}
		draft_ids_100 = []
		draft_ids_80 = []
		draft_ids_all = []

		for draft in Draft.query.filter_by(uid=current_user.uid).filter(Draft.date < first_match.date).order_by(desc(Draft.date)).all():
			picks = [pick.card for pick in Pick.query.filter_by(uid=current_user.uid, draft_id=draft.draft_id)]
			picks = list(modo.clean_card_set(set(picks), multifaced))
			pick_perc = threshold_met(pick_list=picks, played_list=(nb_lands + spells))
			if pick_perc == 100:
				draft_ids_100.append(draft.draft_id)
			elif pick_perc >= 80:
				draft_ids_80.append(draft.draft_id)
			else:
				draft_ids_all.append(draft.draft_id)
		if len(draft_ids_100) > 0:
			draft_ids_dict['possible_draft_ids'] = draft_ids_100
		elif len(draft_ids_80) > 0:
			draft_ids_dict['possible_draft_ids'] = draft_ids_80
		else:
			draft_ids_dict['possible_draft_ids'] = draft_ids_all

		if len(draft_ids_dict['possible_draft_ids']) > 0:
			break

		limited_matches = limited_matches.filter(Match.date > first_match.date).order_by(Match.date)
		first_match = limited_matches.first()
	return first_match.as_dict() | cards_dict | draft_ids_dict
	
@views.route('/associated_draft_id/<match_id>/<draft_id>')
@login_required
def apply_draft_id(match_id, draft_id):
	def threshold_met(pick_list, played_list):
		if not pick_list:
			return False
		condition_met = sum(1 for i in played_list if i in pick_list)
		perc = (condition_met / len(played_list)) * 100
		return perc
	
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return 'Forbidden', 403
	if not current_user.is_authenticated:
		return 'Forbidden', 403
	
	# Add limited match conditions here.
	limited_matches = Match.query.filter_by(uid=current_user.uid, draft_id='NA', p1=current_user.username)
	limited_matches = limited_matches.filter( Match.format.in_(['Cube', 'Booster Draft']) )
	date = Match.query.filter_by(uid=current_user.uid, match_id=match_id).first().date
	limited_matches = limited_matches.filter(Match.date > date).order_by(Match.date)
	next_match = limited_matches.first()

	if draft_id != '0':
		matches = Match.query.filter_by(uid=current_user.uid, match_id=match_id).all()
		for match in matches:
			match.draft_id = draft_id
		try:
			db.session.commit()
		except:
			db.session.rollback()

		match_wins = 0
		match_losses = 0
		associated_matches = Match.query.filter_by(uid=current_user.uid, draft_id=draft_id, p1=current_user.username)
		for match in associated_matches:
			if match.p1_wins > match.p2_wins:
				match_wins += 1
			elif match.p2_wins > match.p1_wins:
				match_losses += 1
		draft = Draft.query.filter_by(uid=current_user.uid, draft_id=draft_id).first()
		draft.match_wins = match_wins
		draft.match_losses = match_losses
		try:
			db.session.commit()
		except:
			db.session.rollback()

	while True:
		if next_match is None:
			return {'match_id':'NA'}

		lands = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																	match_id=next_match.match_id, 
																	casting_player=next_match.p1, 
																	action='Land Drop').order_by(Play.primary_card)]
		nb_lands = [i for i in lands if (i not in ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest'])]
		spells = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																	 match_id=next_match.match_id, 
																	 casting_player=next_match.p1, 
																	 action='Casts').order_by(Play.primary_card)]

		nb_lands = list(modo.clean_card_set(set(nb_lands), multifaced))
		lands = list(modo.clean_card_set(set(lands), multifaced))
		spells = list(modo.clean_card_set(set(spells), multifaced))

		cards_dict = {'lands':[*set(lands)], 'spells':[*set(spells)]}
		draft_ids_dict = {'possible_draft_ids':[]}
		draft_ids_100 = []
		draft_ids_80 = []
		draft_ids_all = []

		for draft in Draft.query.filter_by(uid=current_user.uid).filter(Draft.date < next_match.date).order_by(desc(Draft.date)).all():
			picks = [pick.card for pick in Pick.query.filter_by(uid=current_user.uid, draft_id=draft.draft_id)]
			picks = list(modo.clean_card_set(set(picks), multifaced))
			pick_perc = threshold_met(pick_list=picks, played_list=(nb_lands + spells))
			if pick_perc == 100:
				draft_ids_100.append(draft.draft_id)
			elif pick_perc >= 80:
				draft_ids_80.append(draft.draft_id)
			else:
				draft_ids_all.append(draft.draft_id)
		if len(draft_ids_100) > 0:
			draft_ids_dict['possible_draft_ids'] = draft_ids_100
		elif len(draft_ids_80) > 0:
			draft_ids_dict['possible_draft_ids'] = draft_ids_80
		else:
			draft_ids_dict['possible_draft_ids'] = draft_ids_all

		if len(draft_ids_dict['possible_draft_ids']) > 0:
			break
		
		limited_matches = limited_matches.filter(Match.date > next_match.date).order_by(Match.date)
		next_match = limited_matches.first()
	return next_match.as_dict() | cards_dict | draft_ids_dict

@views.route('/input_options')
@login_required
def input_options():
	ensure_data_loaded()
	return options

@views.route('/export')
@login_required
def export():
	file_name = f'{current_user.email}_Tables.zip'
	blob_client = export_container_client.get_blob_client(file_name)
	
	tables = ['Matches', 'Games', 'Plays', 'Picks', 'Drafts']
	empty_tables = []
	export_cnt = 0
	try:
		pd.DataFrame([i.as_dict() for i in Match.query.filter_by(uid=current_user.uid, p1=current_user.username).all()]).drop('uid', axis=1).to_csv(f'{current_user.email}_Matches.csv', index=False)
		export_cnt += 1
	except KeyError:
		empty_tables.append('Matches')
	try:
		pd.DataFrame([i.as_dict() for i in Game.query.filter_by(uid=current_user.uid, p1=current_user.username).all()]).drop('uid', axis=1).to_csv(f'{current_user.email}_Games.csv', index=False)
		export_cnt += 1
	except KeyError:
		empty_tables.append('Games')
	try:
		pd.DataFrame([i.as_dict() for i in Play.query.filter_by(uid=current_user.uid).all()]).drop('uid', axis=1).to_csv(f'{current_user.email}_Plays.csv', index=False)
		export_cnt += 1
	except KeyError:
		empty_tables.append('Plays')
	try:
		pd.DataFrame([i.as_dict() for i in Pick.query.filter_by(uid=current_user.uid).all()]).drop('uid', axis=1).to_csv(f'{current_user.email}_Picks.csv', index=False)
		export_cnt += 1
	except:
		empty_tables.append('Drafts')
	try:
		pd.DataFrame([i.as_dict() for i in Draft.query.filter_by(uid=current_user.uid).all()]).drop('uid', axis=1).to_csv(f'{current_user.email}_Drafts.csv', index=False)
		export_cnt += 1
	except KeyError:
		empty_tables.append('Draft Picks')

	with zipfile.ZipFile(f'{current_user.email}_Tables.zip', 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
		for i in tables:
			if os.path.exists(f'{current_user.email}_{i}.csv'):
				zipf.write(f'{current_user.email}_{i}.csv', f'{current_user.email}_{i}.csv')
	with open(f'{current_user.email}_Tables.zip', "rb") as data:
		blob_client.upload_blob(data, overwrite=True)
	for i in tables:
		if os.path.exists(f'{current_user.email}_{i}.csv'):
			os.remove(f'{current_user.email}_{i}.csv')
	os.remove(f'{current_user.email}_Tables.zip')

	blob_client = blob_service_client.get_blob_client(container=os.environ.get('EXPORT_CONTAINER_NAME'), blob=file_name)
	sas_token = generate_blob_sas(
		blob_client.account_name,
		blob_client.container_name,
		blob_client.blob_name,
		account_key=blob_service_client.credential.account_key,  # or use connection_string
		permission=BlobSasPermissions(read=True),
		expiry=datetime.datetime.utcnow() + timedelta(hours=24)  # Adjust the expiry time as needed
	)
	
	url = blob_client.url + '?' + sas_token
	return redirect(url)

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
		if (bg_type == 'Limited Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Limited Formats']) )
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

@views.route('/remove', methods=['POST'])
@login_required
def remove():
	removeType = request.form.get('removeType')
	match_ids = request.form.get('removeMatchId').split(',')

	match_size = 0
	game_size = 0
	play_size = 0

	for match_id in match_ids:
		match_size += Match.query.filter_by(uid=current_user.uid, match_id=match_id).count()
		game_size += Game.query.filter_by(uid=current_user.uid, match_id=match_id).count()
		play_size += Play.query.filter_by(uid=current_user.uid, match_id=match_id).count()

		Match.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
		Game.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
		Play.query.filter_by(uid=current_user.uid, match_id=match_id).delete()

		if removeType == 'Ignore':
			newIgnore = Removed(uid=current_user.uid, match_id=match_id, reason='Ignored')
			db.session.add(newIgnore)
		try:
			db.session.commit()
		except:
			db.session.rollback()

	flash(f'{match_size} Matches removed, {game_size} Games removed, {play_size} Plays removed.', category='success')
	return redirect('/table/matches/1')

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
			return [max_streak, f'{max_streak_start_date[5:7]}/{max_streak_start_date[0:4]}', max_streak_end_date]
		else:
			return [max_streak, f'{max_streak_start_date[5:7]}/{max_streak_start_date[0:4]}', f'{max_streak_end_date[5:7]}/{max_streak_end_date[0:4]}']
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
		stats_dict['longest_game'] = [longest_game[1].turns, longest_game[0].date[5:7]+'/'+longest_game[0].date[0:4], longest_game[0].p1_subarch, longest_game[0].p2_subarch]
	else:
		stats_dict['longest_game'] = [0, 'NA', 'NA', 'NA']

	return render_template('profile.html', user=current_user, stats=stats_dict)

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

@views.route('/load_dashboards/<dash_name>', methods=['POST'])
@login_required
def dashboards(dash_name):
	# Ensure data is loaded before using global variables
	ensure_data_loaded()
	
	def match_result(p1_wins, p2_wins):
		if p1_wins == p2_wins:
			return f'NA {p1_wins}-{p2_wins}'
		elif p1_wins > p2_wins:
			return f'Win {p1_wins}-{p2_wins}'
		elif p2_wins > p1_wins:
			return f'Loss {p1_wins}-{p2_wins}'
	def format_string(fmt, limited_format):
		if fmt in options['Limited Formats']:
			return f'{fmt}: {limited_format}'
		return f'{fmt}'

	dashCard = 'Card'
	dashOpponent = 'Opponent'
	dashFormat = 'Format'
	dashLimitedFormat = 'Limited Format'
	dashDeck = 'Deck'
	dashOppDeck = 'Opp. Deck'
	dashDate1 = '1900-01-01'
	dashDate2 = '2999-12-31'
	dashAction = 'Casts'
	if (request.method == 'POST') and (request.form.get('dashName') is not None):
		dashCard = request.form.get('dashCard')
		dashOpponent = request.form.get('dashOpponent')
		dashFormat = request.form.get('dashFormat')
		dashLimitedFormat = request.form.get('dashLimitedFormat')
		dashDeck = request.form.get('dashDeck')
		dashOppDeck = request.form.get('dashOppDeck')
		dashDate1 = request.form.get('dashDate1')
		dashDate2 = request.form.get('dashDate2')
		dashAction = request.form.get('dashAction')

	if dashDate1 == '':
		dashDate1 = '1900-01-01'
	if dashDate2 == '':
		dashDate2 = '2999-12-31'
	inputs = [dashCard, dashOpponent, dashFormat, dashLimitedFormat, dashDeck, dashOppDeck, str(dashDate1) + '-00:00', str(dashDate2) + '-23:59', dashAction]

	table = Match.query.filter(Match.uid == current_user.uid, Match.p1 == current_user.username, Match.date > inputs[6], Match.date < inputs[7])
	if dash_name == 'match-history':
		pass
	elif dash_name == 'match-stats':
		pass
	elif dash_name == 'game-stats':
		table = table.join(Game, (Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)).add_entity(Game)
	elif dash_name == 'play-stats':
		table = table.join(Game, (Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)).add_entity(Game)
		table = table.join(Play, (Play.uid == Game.uid) & (Play.match_id == Game.match_id) & (Play.game_num == Game.game_num)).add_entity(Play)
	elif dash_name == 'opponents':
		pass
	elif dash_name == 'card-data':
		table = table.join(Game, (Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)).add_entity(Game)
		table = table.join(Play, (Play.uid == Game.uid) & (Play.match_id == Game.match_id) & (Play.game_num == Game.game_num)).add_entity(Play)
		table = table.filter(Play.primary_card != 'NA')
		if dashAction != 'Action':
			table = table.filter(Play.action.in_([dashAction]))
	else:
		flash(f'That dashboard page does not exist.', category='error')
		return render_template('index.html', user=current_user)

	if dashCard != 'Card':
		table = table.filter(Play.primary_card == dashCard)
	if dashOpponent != 'Opponent':
		table = table.filter(Match.p2 == dashOpponent)
	if dashFormat != 'Format':
		table = table.filter(Match.format == dashFormat)
	if dashLimitedFormat != 'Limited Format':
		table = table.filter(Match.limited_format == dashLimitedFormat)
	if dashDeck != 'Deck':
		table = table.filter(Match.p1_subarch == dashDeck)
	if dashOppDeck != 'Opp. Deck':
		table = table.filter(Match.p2_subarch == dashOppDeck)

	if len(table.all()) == 0:
		flash(f'Dashboard could not be displayed: Query result was empty. If you have imported data successfully, try changing your filters below.', category='error')
		return render_template('dashboards.html', user=current_user, dash_name=dash_name, inputs=inputs)

	if dash_name == 'match-history':
		table = table.order_by(desc(Match.date)).limit(20)
		df = pd.DataFrame([i.as_dict() for i in table.all()])
		df['Match Result'] = df.apply(lambda x: match_result(p1_wins=x['p1_wins'], p2_wins=x['p2_wins']), axis=1)
		df['Match Format'] = df.apply(lambda x: format_string(fmt=x['format'], limited_format=x['limited_format']), axis=1)
		df = df.rename(columns={'p2':'Opponent', 'p2_subarch':'Opp. Deck', 'p1_subarch':'Deck', 'date':'Date'})
		df = df[['Date','Opponent','Deck','Opp. Deck','Match Result','Match Format']]
		return render_template('dashboards.html', user=current_user, dash_name=dash_name, inputs=inputs, table=[df])
	elif dash_name == 'match-stats':
		df = pd.DataFrame([i.as_dict() for i in table.all()])
		df['Wins'] = df.apply(lambda x: 1 if x['match_winner'] == 'P1' else 0, axis=1)
		df['Losses'] = df.apply(lambda x: 1 if x['match_winner'] == 'P2' else 0, axis=1)
		df['Roll_Wins'] = df.apply(lambda x: 1 if x['roll_winner'] == 'P1' else 0, axis=1)
		df['Roll_Losses'] = df.apply(lambda x: 1 if x['roll_winner'] == 'P2' else 0, axis=1)

		df1 = df.groupby(['format']).agg({'Wins':'sum', 'Losses':'sum'}).reset_index()
		df1 = df1.rename(columns={'format':'Description'})
		df1.loc[-1] = pd.concat([pd.Series({'Description':'Match Format'}), df[['Wins','Losses']].sum()], axis=0)
		df1.index = df1.index + 1
		df1 = df1.sort_index()
		df1['Total'] = df1.apply(lambda x: x['Wins']+x['Losses'], axis=1)
		first_row = df1.iloc[[0]]
		df1 = pd.concat([first_row, df1.iloc[1:].sort_values('Total', ascending=False)])
		df1['Match Win%'] = df1.apply(lambda x: 0.0 if (x['Total'] == 0) else round( (x['Wins']/(x['Total']))*100, 1), axis=1)

		df2 = df.groupby(['match_type']).agg({'Wins':'sum', 'Losses':'sum'}).reset_index()
		df2 = df2.rename(columns={'match_type':'Description'})
		df2.loc[-1] = pd.concat([pd.Series({'Description':'Match Type'}), df[['Wins','Losses']].sum()], axis=0)
		df2.index = df2.index + 1
		df2 = df2.sort_index()
		df2['Total'] = df2.apply(lambda x: x['Wins']+x['Losses'], axis=1)
		first_row = df2.iloc[[0]]
		df2 = pd.concat([first_row, df2.iloc[1:].sort_values('Total', ascending=False)])
		df2['Match Win%'] = df2.apply(lambda x: round( (x['Wins']/(x['Total']))*100, 1), axis=1)

		df3 = df.groupby(['p1_subarch']).agg({'p1':'count', 'Wins':'sum', 'Losses':'sum'}).reset_index()
		df3 = df3.rename(columns={'p1':'Share', 'p1_subarch':'Decks'})
		df3['Total'] = df3.apply(lambda x: x['Wins']+x['Losses'], axis=1)
		df3 = df3.sort_values('Total', ascending=False)
		df3['Match Win%'] = df3.apply(lambda x: 0.0 if (x['Total'] == 0) else round( (x['Wins']/(x['Total']))*100, 1), axis=1)
		df3['Share'] = df3.apply(lambda x: str(x['Share']) + ' - (' + str(round( (x['Share']/df3['Share'].sum())*100)) + '%)', axis=1)
		df3 = df3.drop('Total', axis=1)
		df3 = df3.head(10)

		df4 = df.groupby(['p2_subarch']).agg({'p2':'count', 'Wins':'sum', 'Losses':'sum'}).reset_index()
		df4 = df4.rename(columns={'p2':'Share', 'p2_subarch':'Decks'})
		df4['Total'] = df4.apply(lambda x: x['Wins']+x['Losses'], axis=1)
		df4 = df4.sort_values('Total', ascending=False)
		df4['Win% Against'] = df4.apply(lambda x: 0.0 if ((x['Wins']+x['Losses']) == 0) else round( (x['Wins']/(x['Wins']+x['Losses']))*100, 1), axis=1)
		df4['Share'] = df4.apply(lambda x: str(x['Share']) + ' - (' + str(round( (x['Share']/df4['Share'].sum())*100)) + '%)', axis=1)
		df4 = df4.drop('Total', axis=1)
		df4 = df4.head(10)

		df5 = pd.DataFrame({'Hero Avg.':[round(df['p1_roll'].mean(),2)], 'Opp. Avg.':[round(df['p2_roll'].mean(),2)], 'Die Roll Win%':[round((df['Roll_Wins'].sum()/(df['Roll_Wins'].sum()+df['Roll_Losses'].sum())*100 ),1)]})
		return render_template('dashboards.html', user=current_user, dash_name=dash_name, inputs=inputs, table=[df1, df2, df3, df4, df5])
	elif dash_name == 'game-stats':
		df = pd.DataFrame([i[0].as_dict() | i[1].as_dict() for i in table.all()])
		df['PD_Label'] = df.apply(lambda x: 'Play' if x['on_play'] == 'P1' else 'Draw', axis=1)
		df['PD_Label2'] = 'Overall'
		df['Game_Label'] = df.apply(lambda x: 'Game 1' if x['game_num'] == 1 else ('Game 2' if x['game_num'] == 2 else ('Game 3' if x['game_num'] == 3 else 0)), axis=1)
		df['Game_Label2'] = 'All Games'
		df['Wins'] = df.apply(lambda x: 1 if x['game_winner'] == 'P1' else 0, axis=1)
		df['Losses'] = df.apply(lambda x: 1 if x['game_winner'] == 'P2' else 0, axis=1)

		df1 = df.groupby(['Game_Label', 'PD_Label']).agg({'Wins':'sum', 'Losses':'sum', 'p1':'count', 'p1_mulls':'mean', 'p2_mulls':'mean', 'turns':'mean'}).reset_index()
		df1_total = df.groupby(['Game_Label', 'PD_Label2']).agg({'Wins':'sum', 'Losses':'sum', 'p1':'count', 'p1_mulls':'mean', 'p2_mulls':'mean', 'turns':'mean'}).reset_index()
		df1_total = df1_total.rename(columns={'PD_Label2':'PD_Label'})
		df2 = df.groupby(['Game_Label2', 'PD_Label']).agg({'Wins':'sum', 'Losses':'sum', 'p1':'count', 'p1_mulls':'mean', 'p2_mulls':'mean', 'turns':'mean'}).reset_index()
		df2_total = df.groupby(['Game_Label2', 'PD_Label2']).agg({'Wins':'sum', 'Losses':'sum', 'p1':'count', 'p1_mulls':'mean', 'p2_mulls':'mean', 'turns':'mean'}).reset_index()
		df2 = df2.rename(columns={'Game_Label2':'Game_Label', 'PD_Label2':'PD_Label'})
		df2_total = df2_total.rename(columns={'Game_Label2':'Game_Label', 'PD_Label2':'PD_Label'})
		df3 = pd.concat([df1, df1_total, df2, df2_total]).reset_index(drop=True)
		df3['p1_mulls'] = df3.apply(lambda x: round(x['p1_mulls'],2), axis=1)
		df3['p2_mulls'] = df3.apply(lambda x: round(x['p2_mulls'],2), axis=1)
		df3['turns'] = df3.apply(lambda x: round(x['turns'],2), axis=1)
		df3['Win%'] = df3.apply(lambda x: 0.0 if ((x['Wins']+x['Losses']) == 0) else round( (x['Wins']/(x['Wins']+x['Losses']))*100, 1), axis=1)
		df3['Ordered'] = pd.Categorical(df3['PD_Label'], categories=['Play', 'Draw', 'Overall'], ordered=True)
		df3 = df3.rename(columns={'p1':'Total', 'p1_mulls':'Mulls/G', 'p2_mulls':'Opp Mulls/G', 'turns':'Turns/G'})
		df3 = df3.sort_values(['Game_Label', 'Ordered'], ascending=True).drop('Ordered', axis=1).reset_index(drop=True)

		return render_template('dashboards.html', user=current_user, dash_name=dash_name, inputs=inputs, table=[df3])
	elif dash_name == 'play-stats':
		df = pd.DataFrame([i[0].as_dict() | i[1].as_dict() | i[2].as_dict() for i in table.all()])
		df = df[(df.casting_player == df.p1)]

		dict1 = {}
		for i in df.format.unique():
			games_cnt = len(df[(df.format == i)].groupby(['match_id','game_num']))
			dict1[i] = {'Total':[],'Per Game':[], 'Games':games_cnt}
			for j in ['Land Drop','Casts','Activated Ability','Triggers']:
				try:
					dict1[i]['Total'].append(str(int(df[(df.format == i) & (df.action == j)].groupby('action').size().item())))
				except ValueError:
					dict1[i]['Total'].append('0')
			dict1[i]['Total'].append(str(int(df[(df.format == i)].attackers.sum())))
			dict1[i]['Total'].append(str(int(df[(df.format == i)].cards_drawn.sum())))
			for j in dict1[i]['Total']:
				dict1[i]['Per Game'].append(str(round(int(j)/games_cnt,2)))

		dict2 = {}
		for i in df.p1_subarch.unique():
			games_cnt = len(df[(df.p1_subarch == i)].groupby(['match_id','game_num']))
			dict2[i] = {'Total':[],'Per Game':[], 'Games':games_cnt}
			for j in ['Land Drop','Casts','Activated Ability','Triggers']:
				try:
					dict2[i]['Total'].append(str(int(df[(df.p1_subarch == i) & (df.action == j)].groupby('action').size().item())))
				except ValueError:
					dict2[i]['Total'].append('0')
			dict2[i]['Total'].append(str(int(df[(df.p1_subarch == i)].attackers.sum())))
			dict2[i]['Total'].append(str(int(df[(df.p1_subarch == i)].cards_drawn.sum())))
			for j in dict2[i]['Total']:
				dict2[i]['Per Game'].append(str(round(int(j)/games_cnt,2)))

		dict3 = {}
		for i in df.p2_subarch.unique():
			games_cnt = len(df[(df.p2_subarch == i)].groupby(['match_id','game_num']))
			dict3[i] = {'Total':[],'Per Game':[], 'Games':games_cnt}
			for j in ['Land Drop','Casts','Activated Ability','Triggers']:
				try:
					dict3[i]['Total'].append(str(int(df[(df.p2_subarch == i) & (df.action == j)].groupby('action').size().item())))
				except ValueError:
					dict3[i]['Total'].append('0')
			dict3[i]['Total'].append(str(int(df[(df.p2_subarch == i)].attackers.sum())))
			dict3[i]['Total'].append(str(int(df[(df.p2_subarch == i)].cards_drawn.sum())))
			for j in dict3[i]['Total']:
				dict3[i]['Per Game'].append(str(round(int(j)/games_cnt,2)))

		dict4 = {}
		for i in df.turn_num.unique():
			dict4[i] = []
			ga_cnt = 0
			for j in ['Land Drop','Casts','Activated Ability','Triggers']:
				try:
					action_cnt = int(df[(df.turn_num == i) & (df.action == j)].groupby('action').size().item())
				except ValueError:
					action_cnt = 0
				ga_cnt += action_cnt
				dict4[i].append(action_cnt)
			ga_cnt += int(df[(df.turn_num == i)].attackers.sum())
			dict4[i].append(int(df[(df.turn_num == i)].attackers.sum()))
			dict4[i].append(int(df[(df.turn_num == i)].cards_drawn.sum()))
			dict4[i].append(ga_cnt)

		df1 = pd.DataFrame(columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws'])
		for i in sorted(dict1.items(),key=lambda x: x[1]['Games'], reverse=True):
			df1 = pd.concat([df1,
							 pd.DataFrame([[i[0],'Total']+i[1]['Total']],columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws']),
							 pd.DataFrame([[str(i[1]['Games'])+' Games','Per Game']+i[1]['Per Game']],columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws'])],
							 ignore_index=True)

		df2 = pd.DataFrame(columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws'])
		for i in sorted(dict2.items(),key=lambda x: x[1]['Games'], reverse=True):
			df2 = pd.concat([df2,
							 pd.DataFrame([[i[0],'Total']+i[1]['Total']],columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws']),
							 pd.DataFrame([[str(i[1]['Games'])+' Games','Per Game']+i[1]['Per Game']],columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws'])],
							 ignore_index=True)
		df2 = df2.head(20)

		df3 = pd.DataFrame(columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws'])
		for i in sorted(dict3.items(),key=lambda x: x[1]['Games'], reverse=True):
			df3 = pd.concat([df3,
							 pd.DataFrame([[i[0],'Total']+i[1]['Total']],columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws']),
							 pd.DataFrame([[str(i[1]['Games'])+' Games','Per Game']+i[1]['Per Game']],columns=['','','Land Drop','Casts','Activates','Triggers','Attacks','Draws'])],
							 ignore_index=True)
		df3 = df3.head(20)

		df4 = pd.DataFrame(columns=['','Land Drop','Casts','Activates','Triggers','Attacks','Draws','Total GA'])
		for i in sorted(dict4.items(),key=lambda x: x[0], reverse=False):
			df4 = pd.concat([df4,
							 pd.DataFrame([['Turn '+str(i[0])]+i[1]],columns=['','Land Drop','Casts','Activates','Triggers','Attacks','Draws','Total GA'])],
							 ignore_index=True)

		return render_template('dashboards.html', user=current_user, dash_name=dash_name, inputs=inputs, table=[df1,df2,df3,df4]) 
	elif dash_name == 'opponents':
		pass
	elif dash_name == 'card-data':
		df_pre = pd.DataFrame([i[0].as_dict() | i[1].as_dict() | i[2].as_dict() for i in table.filter(Game.game_num.in_([1])).all()])
		df_post = pd.DataFrame([i[0].as_dict() | i[1].as_dict() | i[2].as_dict() for i in table.filter(Game.game_num.in_([2,3])).all()])

		if len(df_pre) == 0:
			df1 = pd.DataFrame({'Primary_Card':[], 'Games Won':[], 'Games Played':[], 'Game Win%':[]})
		else:
			df_pre['Games Won'] = df_pre.apply(lambda x: x['match_id']+str(x['game_num']) if x['game_winner'] == 'P1' else None, axis=1)
			df_pre['Games Played'] = df_pre.apply(lambda x: x['match_id']+str(x['game_num']), axis=1)
			df1 = df_pre.groupby(['primary_card']).agg({'Games Won':'nunique', 'Games Played':'nunique'}).reset_index()
			df1['Game Win%'] = df1.apply(lambda x: 0.0 if (x['Games Played'] == 0) else round((x['Games Won']/x['Games Played'])*100,1), axis=1)
			df1 = df1.sort_values(by='Games Played', ascending=False).reset_index(drop=True)
			df1.rename(columns={'primary_card':'Primary_Card'}, inplace=True)
		
		if len(df_post) == 0:
			df2 = pd.DataFrame({'Primary_Card':[], 'Games Won':[], 'Games Played':[], 'Game Win%':[]})
		else:
			df_post['Games Won'] = df_post.apply(lambda x: x['match_id']+str(x['game_num']) if x['game_winner'] == 'P1' else None, axis=1)
			df_post['Games Played'] = df_post.apply(lambda x: x['match_id']+str(x['game_num']), axis=1)
			df2 = df_post.groupby(['primary_card']).agg({'Games Won':'nunique', 'Games Played':'nunique'}).reset_index()
			df2['Game Win%'] = df2.apply(lambda x: 0.0 if (x['Games Played'] == 0) else round((x['Games Won']/x['Games Played'])*100,1), axis=1)
			df2 = df2.sort_values(by='Games Played', ascending=False).reset_index(drop=True)
			df2.rename(columns={'primary_card':'Primary_Card'}, inplace=True)

		return render_template('dashboards.html', user=current_user, dash_name=dash_name, inputs=inputs, table=[df1.head(20), df2.head(20)]) 

	return render_template('dashboards.html', user=current_user, dash_name=dash_name, inputs=inputs)

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

@views.route('/dashboards/<dash_name>', methods=['GET', 'POST'])
@login_required
def load_dash(dash_name):
	return render_template('load-dash.html', user=current_user, dash_name=dash_name)

@views.route('/data_dictionary', methods=['GET'])
def data_dict():
	return render_template('data-dict.html', user=current_user)

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
