import logging
import time
from datetime import date, datetime, timezone
from functools import wraps

import requests

from app import db
from app.models import Game, Season, Team

logger = logging.getLogger(__name__)


def rate_limit_decorator(max_retries=3, base_delay=1.0, backoff_factor=2.0):
    """
    Decorator to handle API rate limiting with exponential backoff
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    response = func(self, *args, **kwargs)

                    # Check for rate limiting
                    if hasattr(response, "status_code"):
                        if response.status_code == 429:  # Too Many Requests
                            retry_after = int(
                                response.headers.get(
                                    "Retry-After",
                                    base_delay * (backoff_factor**attempt),
                                )
                            )
                            logger.warning(
                                f"Rate limited. Waiting {retry_after}s before retry {attempt + 1}/{max_retries}"
                            )
                            time.sleep(retry_after)
                            continue
                        elif response.status_code >= 500:  # Server errors
                            delay = base_delay * (backoff_factor**attempt)
                            logger.warning(
                                f"Server error {response.status_code}. Waiting {delay}s before retry {attempt + 1}/{max_retries}"
                            )
                            time.sleep(delay)
                            continue

                    return response

                except requests.exceptions.RequestException as e:
                    delay = base_delay * (backoff_factor**attempt)
                    logger.warning(
                        f"Request failed: {e}. Waiting {delay}s before retry {attempt + 1}/{max_retries}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                    else:
                        raise

            raise Exception(f"Max retries ({max_retries}) exceeded")

        return wrapper

    return decorator


class DataSync:
    """
    Handles synchronization of NFL data from external APIs with rate limiting and failsafe mechanisms
    """

    def __init__(self, api_base_url=None):
        self.api_base_url = (
            api_base_url or "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "NFL-Pickem-App/1.0"})

        # Rate limiting configuration
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Minimum 500ms between requests
        self.max_requests_per_minute = 60  # Conservative limit
        self.request_timestamps = []

    def _enforce_rate_limit(self):
        """Enforce rate limiting before making requests"""
        current_time = time.time()

        # Remove timestamps older than 1 minute
        self.request_timestamps = [
            ts for ts in self.request_timestamps if current_time - ts < 60
        ]

        # Check if we're at the request limit
        if len(self.request_timestamps) >= self.max_requests_per_minute:
            sleep_time = 60 - (current_time - self.request_timestamps[0])
            if sleep_time > 0:
                logger.info(f"Rate limit reached. Sleeping for {sleep_time:.1f}s")
                time.sleep(sleep_time)
                self.request_timestamps = []

        # Enforce minimum interval between requests
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)

        # Update tracking
        self.last_request_time = time.time()
        self.request_timestamps.append(self.last_request_time)
        self.request_count += 1

    @rate_limit_decorator(max_retries=3, base_delay=2.0)
    def _make_api_request(self, url, params=None):
        """Make API request with rate limiting and retry logic"""
        self._enforce_rate_limit()

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            logger.warning(f"Request timeout for {url}")
            raise
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error for {url}")
            raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(f"Rate limited: {url}")
                raise
            elif e.response.status_code >= 500:
                logger.warning(f"Server error {e.response.status_code}: {url}")
                raise
            else:
                logger.error(f"HTTP error {e.response.status_code}: {url}")
                raise

    def get_rate_limit_status(self):
        """Get current rate limit status"""
        current_time = time.time()
        # Clean old timestamps
        self.request_timestamps = [
            ts for ts in self.request_timestamps if current_time - ts < 60
        ]

        return {
            "total_requests": self.request_count,
            "requests_last_minute": len(self.request_timestamps),
            "max_requests_per_minute": self.max_requests_per_minute,
            "time_since_last_request": (
                current_time - self.last_request_time if self.last_request_time else 0
            ),
            "min_request_interval": self.min_request_interval,
        }

    def sync_season_data(self, year):
        """Sync all data for a given season"""
        try:
            logger.info(f"Starting sync for {year} season")

            # Create or get season
            season = self._create_or_update_season(year)

            # Sync teams
            teams = self._sync_teams(season)

            # Sync games
            games = self._sync_games(season, teams)

            db.session.commit()
            logger.info(
                f"Successfully synced {year} season: {len(teams)} teams, {len(games)} games"
            )

            return True, f"Synced {len(teams)} teams and {len(games)} games"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error syncing season data: {str(e)}")
            return False, str(e)

    def _create_or_update_season(self, year):
        """Create or update season record"""
        season = Season.query.filter_by(year=year).first()

        if not season:
            # Create new season with estimated dates
            start_date = date(year, 9, 1)  # Rough estimate
            end_date = date(year + 1, 2, 15)  # Rough estimate

            season = Season.create_season(year, start_date, end_date)
            logger.info(f"Created new season for {year}")

        return season

    def _sync_teams(self, season):
        """Sync teams for the season"""
        try:
            # Get teams from ESPN API
            url = f"{self.api_base_url}/teams"
            response = self._make_api_request(url)

            data = response.json()
            teams = []

            for team_data in (
                data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
            ):
                team_info = team_data.get("team", {})

                # Check if team already exists for this season
                existing_team = Team.query.filter_by(
                    season_id=season.id,
                    abbreviation=team_info.get("abbreviation", "").upper(),
                ).first()

                if existing_team:
                    # Update existing team
                    team = existing_team
                else:
                    # Create new team
                    team = Team(season_id=season.id)
                    db.session.add(team)

                # Update team data
                team.name = team_info.get("name", "")
                team.city = team_info.get("location", "")
                team.abbreviation = team_info.get("abbreviation", "").upper()
                team.espn_id = str(team_info.get("id", ""))

                # Parse conference/division from display name
                display_name = team_info.get("displayName", "")
                if "AFC" in display_name or "NFC" in display_name:
                    team.conference = "AFC" if "AFC" in display_name else "NFC"

                # Get team colors and logo
                if "logos" in team_info and team_info["logos"]:
                    team.logo_url = team_info["logos"][0].get("href", "")

                if "color" in team_info:
                    team.primary_color = f"#{team_info['color']}"

                if "alternateColor" in team_info:
                    team.secondary_color = f"#{team_info['alternateColor']}"

                teams.append(team)

            return teams

        except Exception as e:
            logger.error(f"Error syncing teams: {str(e)}")
            raise

    def _sync_games(self, season, teams):
        """Sync games for the season"""
        try:
            games = []

            # Get games for each week (estimate 18 regular season weeks + 4 playoff weeks)
            for week in range(1, 23):  # Weeks 1-18 regular, 19-22 playoffs
                week_games = self._sync_week_games(season, week, teams)
                games.extend(week_games)

            return games

        except Exception as e:
            logger.error(f"Error syncing games: {str(e)}")
            raise

    def _sync_week_games(self, season, week, teams):
        """Sync games for a specific week"""
        try:
            # Create team lookup by ESPN ID
            team_lookup = {team.espn_id: team for team in teams if team.espn_id}

            url = f"{self.api_base_url}/scoreboard"
            params = {
                "seasontype": (
                    2 if week <= 18 else 3
                ),  # 2 = regular season, 3 = playoffs
                "week": week if week <= 18 else week - 18,
            }

            response = self._make_api_request(url, params=params)

            data = response.json()
            games = []

            for game_data in data.get("events", []):
                competitions = game_data.get("competitions", [])
                if not competitions:
                    continue

                game_info = competitions[0]  # First (and usually only) competition

                # Get teams
                competitors = game_info.get("competitors", [])
                if len(competitors) != 2:
                    continue

                home_team = None
                away_team = None

                for competitor in competitors:
                    team_id = str(competitor.get("team", {}).get("id", ""))
                    is_home = competitor.get("homeAway") == "home"

                    if team_id in team_lookup:
                        if is_home:
                            home_team = team_lookup[team_id]
                        else:
                            away_team = team_lookup[team_id]

                if not home_team or not away_team:
                    continue

                # Check if game already exists
                existing_game = Game.query.filter_by(
                    season_id=season.id,
                    week=week,
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                ).first()

                if existing_game:
                    game = existing_game
                else:
                    game = Game(
                        season_id=season.id,
                        week=week,
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                    )
                    db.session.add(game)

                # Update game data
                game.espn_id = str(game_data.get("id", ""))

                # Parse game time
                game_date = game_data.get("date")
                if game_date:
                    game.game_time = datetime.fromisoformat(
                        game_date.replace("Z", "+00:00")
                    )

                # Update scores if available
                status = game_info.get("status", {})
                if status.get("type", {}).get("completed"):
                    game.is_final = True

                    for competitor in competitors:
                        score = competitor.get("score", 0)
                        is_home = competitor.get("homeAway") == "home"

                        if is_home:
                            game.home_score = int(score) if score else 0
                        else:
                            game.away_score = int(score) if score else 0

                games.append(game)

            return games

        except Exception as e:
            logger.error(f"Error syncing week {week} games: {str(e)}")
            return []

    def update_live_scores(self):
        """Update scores for ongoing games"""
        try:
            current_season = Season.get_current_season()
            if not current_season:
                return False, "No active season"

            # Get games that might be in progress
            ongoing_games = (
                Game.query.filter_by(season_id=current_season.id, is_final=False)
                .filter(Game.game_time <= datetime.now(timezone.utc))
                .all()
            )

            updates = 0
            for game in ongoing_games:
                if self._update_game_score(game):
                    updates += 1

            db.session.commit()
            return True, f"Updated {updates} games"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating live scores: {str(e)}")
            return False, str(e)

    def _update_game_score(self, game):
        """Update score for a single game"""
        try:
            if not game.espn_id:
                return False

            url = f"{self.api_base_url}/summary"
            params = {"event": game.espn_id}

            response = self._make_api_request(url, params=params)

            data = response.json()
            competition = data.get("header", {}).get("competition", {})

            # Check if game is complete
            status = competition.get("status", {})
            is_final = status.get("type", {}).get("completed", False)

            # Get current scores
            competitors = competition.get("competitors", [])
            home_score = None
            away_score = None

            for competitor in competitors:
                score = competitor.get("score", 0)
                is_home = competitor.get("homeAway") == "home"

                if is_home:
                    home_score = int(score) if score else 0
                else:
                    away_score = int(score) if score else 0

            # Check if anything changed
            score_changed = (
                home_score is not None
                and away_score is not None
                and (game.home_score != home_score or game.away_score != away_score)
            )
            status_changed = is_final != game.is_final

            if score_changed or status_changed:
                # Update game data
                if home_score is not None:
                    game.home_score = home_score
                if away_score is not None:
                    game.away_score = away_score
                game.is_final = is_final

                # Note: We don't call game.update_score() here to avoid
                # updating picks multiple times. The scheduler service
                # handles pick updates in _process_completed_game()

                return True

            return False

        except Exception as e:
            logger.error(f"Error updating game {game.id}: {str(e)}", exc_info=True)
            return False
