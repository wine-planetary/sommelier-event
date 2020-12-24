#-*-coding:utf-8-*-
import os
import tweepy
import gspread
import datetime
import requests
import urllib.parse
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from twitter_text import parse_tweet
from oauth2client.service_account import ServiceAccountCredentials

rootdir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(os.path.dirname(rootdir), ".env")
credential_json_path = os.path.join(rootdir, "credentials.json")
load_dotenv(env_path)

today = datetime.date.today()
week = ["月", "火", "水", "木", "金", "土", "日"]
target_venue = ["東京", "神奈川", "千葉", "埼玉", "本部", "賛助・友好団体"]

scheme = "https"
netloc = "www.sommelier.jp"
path = "/event"

def get_event_page(page):
    params = fragment = None
    query_dict = {
             "viewType" : "l",
         "calenderYear" : today.year,
        "calenderMonth" : today.month,
                 "page" : page,
    }
    query = urllib.parse.urlencode(query_dict)
    url = urllib.parse.urlunparse((scheme, netloc, path, params, query, fragment))
    response = requests.get(url)
    # 正しいレスポンスが返ってきた場合
    if response.ok:
        soup = BeautifulSoup(response.text, "html.parser")
        return soup
    else:
        return False

def parse_event_page(soup):
    event_list = []
    event_li_list = soup.find(id="e_list_area").find("ul", class_="event_list").findAll("li")
    for event_li in event_li_list:
        event_month, event_day = map(int, event_li.find(class_="eve_data").text.split("/"))
        event_date = datetime.date(today.year, int(event_month), int(event_day))
        # 年を超す場合
        if (event_date - today).days < 0:
            event_date = datetime.date(today.year + 1, int(event_month), int(event_day))
        event_venue = event_li.find(class_="eve_name").text
        event_name = event_li.find(class_="eve_txt").find("a").text.replace("\u3000", "")
        event_path = event_li.find(class_="eve_txt").find("a").get("href")
        event_id = os.path.basename(event_path)
        event_dict = {
               "id" : event_id,
             "date" : event_date,
            "venue" : event_venue,
             "name" : event_name,
             "path" : event_path,
        }
        event_list.append(event_dict)
    return event_list

def write_spreadsheet(event_list):
    # spreadsheetにログイン
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(credential_json_path, scope)
    gc = gspread.authorize(credentials)
    SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY")
    worksheet = gc.open_by_key(SPREADSHEET_KEY).sheet1
    # 1行目のイベントIDを取得
    registered_id_list = worksheet.col_values(1)
    # url作成用
    params = query = fragment = None
    # 新しいイベントがあった際に格納する
    new_event_list = []
    for event in event_list:
        event_id = event["id"]
        if event_id not in registered_id_list:
            event_date = event["date"].strftime("%Y/%m/%d")
            event_venue = event["venue"]
            event_name = event["name"]
            event_path = os.path.join(path, event["path"])
            event_url = urllib.parse.urlunparse((scheme, netloc, event_path, params, query, fragment))
            # spreadsheetに行追加
            event_row = [event_id, event_date, event_venue, event_name, event_url]
            worksheet.append_row(event_row)
            # 新しいイベントがあったのでflgをtrueに
            new_event_list.append(event)
    return new_event_list

def filter_event(event_list):
    if len(event_list) == 0:
        return False
    for event in event_list:
        venue = event["venue"]
        if venue in target_venue:
            return True
    else:
        return False

def make_tweet(new_event_list):
    tweet_content = "[自動]ソムリエ協会のイベントが更新されました！"
    tweet_list = []
    for event in new_event_list:
        event_venue = event["venue"]
        if event_venue in target_venue:
            event_name = event["name"]
            event_date = event["date"]
            # locale設定すると文字化けしてしまったので泣く泣く
            event_date_str = "%s月%s日(%s)" % (event_date.month, event_date.day, week[event_date.weekday()])
            tweet_sentence = "%s %s %s" % (event_venue, event_date_str, event_name)
            tweet_content_new = "%s\n%s" % (tweet_content, tweet_sentence)
            if parse_tweet(tweet_content_new).valid:
                tweet_content = tweet_content_new
            else:
                tweet_list.append(tweet_content)
                tweet_content = tweet_sentence
    tweet_list.append(tweet_content)
    return tweet_list

def tweet(tweet_list):
    auth = tweepy.OAuthHandler(os.environ["CONSUMER_KEY"], os.environ["CONSUMER_SECRET"])
    auth.set_access_token(os.environ["ACCESS_TOKEN"], os.environ["ACCESS_SECRET"])
    api = tweepy.API(auth)
    reply_id = None
    for tweet in tweet_list:
        response = api.update_status(tweet, in_reply_to_status_id=reply_id)
        reply_id = response.id

def main(event, context):
    event_list = []
    #とりあえず10ページほど探索
    for page in range(1, 11):
        print(page)
        soup = get_event_page(page)
        if soup:
            event_list_page = parse_event_page(soup)
            event_list.extend(event_list_page)
        else:
            break
    new_event_list = write_spreadsheet(event_list)
    if filter_event(new_event_list):
        tweet_list = make_tweet(new_event_list)
        tweet(tweet_list)

if __name__ == "__main__":
    main(None, None)
