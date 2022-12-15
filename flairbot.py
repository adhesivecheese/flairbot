from loguru import logger
import re
from sys import stdout
from time import sleep
import datetime

import praw
from prawcore.exceptions import (RequestException, ResponseException,
                                 ServerError)

from database import session, Themes, Flairs, EventsTeam
from messages import *

logger.remove() # remove the default logger
logger.add("db.log", rotation="1 week", backtrace=True, diagnose=True, level="INFO")
logger.add(stdout, colorize=True, format="<green>{time}</green> <level>{message}</level>", backtrace=True, diagnose=True)


def checkForEvent(post):
	def updateFlairTable(flair, sub):
		theme_key = flair.flair_key
		theme_key = theme_key.replace(" ","%20")

		content = sub.wiki['moderation/flair'].content_md
		content = content.split("---|---")
		
		content[3] = f"\n[{flair.flair_text}](https://reddit.com/message/compose/?to=dirty-penpal-bot&subject=theme-flair&message={theme_key}) | [{datetime.date.strftime(datetime.datetime.fromtimestamp(int(post.created_utc)), '%B %-d, %Y')}](https://reddit.com{post.permalink})" + content[3]

		reassembled = ""
		for part in content:
			reassembled += part + "---|---"
		reassembled = reassembled[:-7]
		sub.wiki['moderation/flair'].edit(content=reassembled)

	def updateDatabase(post, kind):
		def cutText(text, start, end):
			start = text.find(start) + len(start)
			end = text.find(end)
			return text[start:end]

		postText = post.selftext
		title = post.title.lower()

		if kind == "theme":
			try:
				flairbotlink = re.search("flair, \*\*\[(.*?)\)", postText).group(0)
				flairbotlink = f"[{flairbotlink})"
				flair_key = cutText(flairbotlink, "&message=", ")")
				flair_text = cutText(flairbotlink, "flair, **[", "]")
				title = title.strip("[event]")
				title = title.strip("[theme]")
				theme_tag = cutText(title,"[","]")
				try:
					newflair = Themes(
						flair_key = flair_key,
						created_utc = post.created_utc,
						post_id = post.id,
						theme_tag = theme_tag,
						flair_text = flair_text
					)
					session.add(newflair)
					session.commit()
					logger.info(f"Flair(key={flair_key}, tag={theme_tag}, flair={flair_text}) set")
				except:
					logger.error(f"Database could not be updated")
					session.rollback()
				try:
					updateFlairTable(newflair, post.subreddit)
				except:
					logger.error(f"Flair Table could not be updated")

			except:
				logger.error(f"No appropriate Flair Line found in {kind} {post.id}!")
				#TODO notify
				return
		else:
			currentPost = session.query(Flairs).filter_by(flair_key=kind).first()
			currentPost.post_id=post.id
			session.add(currentPost)
			session.commit()


	title = post.title.lower()
	if not title.startswith("[event]") and not title.startswith("[theme]"): return
	if "meta monday" in title: 
		updateDatabase(post,"metas")
		return
	if "workshop wednesday" in title:
		updateDatabase(post,"workshops")
		return
	if "open forum friday" in title:
		updateDatabase(post,"forums")
		return
	if "theme sunday" in title:
		updateDatabase(post,"theme")
		return
	if "music monday" in title:
		updateDatabase(post,"musicmonday")
		return
	if "book club" in title:
		updateDatabase(post,"bookclub")
		return


def checkPrivateMessage(message):
	eligible = False
	if message.subject == "flair":
		logger.debug(f"checking theme-flair message {message}")
		flair = session.query(Themes).filter(Themes.flair_key==message.body).first()
		if not flair:
			message.reply(invalidMessage)
			message.mark_read()

		max_eligibility_age = flair.created_utc + (86400*7)

		for comment in message.author.comments.new(limit=None):
			if comment.created_utc < flair.created_utc: break
			try:
				if comment.removed: continue
			except: continue
			if comment.parent_id != f"t3_{flair.post_id}": continue
			if comment.created_utc > max_eligibility_age: continue
			if len(comment.body.split(" ")) < 50: continue
			eligible = True
		if not eligible:
			logger.debug(f"Not Eligible by Comment. Checking Submissions")
			for post in message.author.submissions.new(limit=None):
				logger.debug(f"Flair created: {flair.created_utc}, Post Created: {post.created_utc}")
				logger.debug(f"Flair sub: {flair.sub_requirement}, Post Created: {post.subreddit.display_name}")
				logger.debug(post.title)
				if post.created_utc < flair.created_utc and not post.pinned: break
				if post.subreddit.display_name != flair.sub_requirement: continue
				if post.removed: continue
				logger.debug(post.title)
				if f"[{flair.theme_tag.lower()}]" in post.title.lower():
					eligible = True
					break

	elif message.subject == "standard-flair":
		flair = session.query(Flairs).filter(Flairs.flair_key==message.body).first()
		max_eligibility_age = flair.created_utc + (86400*7)

		for comment in message.author.comments.new(limit=None):
			if comment.subreddit.display_name != flair.sub_requirement: continue
			if comment.removed: continue
			if comment.created_utc < flair.created_utc: break
			if flair.post_id:
				if comment.parent_id != f"t3_{flair.post_id}": continue
				if flair.recurring == 1:
					if comment.created_utc > max_eligibility_age: continue
					else:
						eligible = True
						break
			else:
				if flair.age_requirement:
					minimum_eligible_time = message.created_utc - flair.age_requirement
					if comment.created_utc < minimum_eligible_time:
						eligible = True
						break
		if not eligible:
			for post in message.author.submissions.new(limit=None):
				if post.subreddit != flair.sub_requirement: continue
				if post.removed: continue
				if post.created_utc < flair.created_utc: break
				if flair.age_requirement:
					minimum_eligible_time = message.created_utc - flair.age_requirement
					if post.created_utc < minimum_eligible_time:
						eligible = True
						break
				else:
					eligible = True
					break

	elif "flair" in message.subject and "re:" not in message.subject:
		message.reply(malformedMessage)
		message.mark_read()
		logger.info(f"{message.author} sent a malformed flair request.")
		return
	else: return

	if eligible:
		if flair.flair_class:
			sub.flair.set(redditor=message.author, text=flair.flair_text, css_class=flair.flair_class)
		else:
			sub.flair.set(redditor=message.author, text=flair.flair_text)
		message.reply(flairSetMessage.format(flair=flair.flair_text))
		message.mark_read()
		logger.info(f"Set flair {flair.flair_text} for {message.author}.")
	else:
		message.reply(ineligibleMessage)
		message.mark_read()
		logger.info(f"{message.author} requested {flair.flair_text} but does not meet eligibility requirements.")


def updateTeam():
	return [x[0] for x in session.query(EventsTeam.username).filter_by(currently_authorized=1).all()]


def logic(sub):
	logger.info("Starting live streams")
	postStream = sub.stream.submissions(pause_after=-1)
	inboxStream = sub._reddit.inbox.stream(pause_after=-1)
	streamsAlive = True

	eventsTeam = updateTeam()

	while streamsAlive == True:
		try:
			for post in postStream:
				if post is not None:
					if post.author.name in eventsTeam: checkForEvent(post)
				else:
					break
			for message in inboxStream:
				if message is not None:
					if message.new == True:	checkPrivateMessage(message)
				else:
					break

		except RequestException as e:
			logger.error(f'Caught praw RequestException: {str(e)}')
			streamsAlive=False
			return
		except ResponseException as e:
			logger.error(f'Caught praw ResponseException: {str(e)}')
			streamsAlive=False
			return
		except KeyboardInterrupt:
			logger.info('Keyboard interrupt detected. Goodbye!')
			exit()


while True:
	try:
		r = praw.Reddit("skynet")
		r.validate_on_submit = True
		sub = r.subreddit("dirtypenpals")
		logic(sub)
	except KeyboardInterrupt:
		logger.info('Keyboard interrupt detected. Goodbye!')
		exit()
	except ServerError as e:
		logger.error(f"Caught ServerError: {str(e)}")
		logger.debug('Ran into an error. Waiting one minute.')
		sleep(60)
		logger.debug('Attempting to continue.')
		continue
	except RequestException as e:
		logger.error(f'Caught RequestException: {str(e)}')
		logger.debug('Ran into an error. Waiting one minute.')
		sleep(60)
		logger.debug('Attempting to continue.')
		continue
	except Exception as e:
		logger.error(f'Caught unknown exception: {str(e)}')
		logger.debug('Ran into an error. Waiting one minute.')
		sleep(60)
		logger.debug('Attempting to continue.')
		continue
