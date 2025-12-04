#!/usr/bin/env python3
"""
SlackBotEnum - Slack Bot Token Enumeration Tool
Enumerates all accessible data using a Slack bot token (xoxb-).
"""

import argparse
import json
import pathlib
import time
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

import colorama
import requests
import termcolor

from constants import get_user_agent


#############
# Constants #
#############
SLACK_API_BASE = "https://slack.com/api"
MAX_RESULTS_PER_PAGE = 200
RATE_LIMIT_SLEEP = 10


class SlackBotEnumerator:
    """
    Enumerates accessible Slack data using a bot token.
    """

    def __init__(self, token: str, output_dir: Optional[str] = None, verbose: bool = False):
        self.token = token
        self.verbose = verbose
        self.user_agent = get_user_agent()
        self.headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': self.user_agent,
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        # Will be populated after auth.test
        self.bot_info: Dict = {}
        self.team_info: Dict = {}
        self.scopes: List[str] = []
        
        # Output directory
        self.output_dir = output_dir
        
        # Collected data
        self.data = {
            'auth': {},
            'team': {},
            'users': [],
            'channels': [],
            'conversations': {},
            'files': [],
            'emoji': {},
            'bookmarks': {},
            'pins': {},
            'usergroups': [],
            'bots': []
        }

    def _api_call(self, method: str, params: Optional[Dict] = None, 
                  json_data: Optional[Dict] = None) -> Optional[Dict]:
        """Make a Slack API call with rate limit handling."""
        url = f"{SLACK_API_BASE}/{method}"
        
        while True:
            try:
                if json_data:
                    response = requests.post(url, headers=self.headers, json=json_data)
                else:
                    response = requests.get(url, headers=self.headers, params=params or {})
                
                result = response.json()
                
                if result.get('ok') is False:
                    error = result.get('error', 'unknown')
                    if error == 'ratelimited':
                        retry_after = int(response.headers.get('Retry-After', RATE_LIMIT_SLEEP))
                        self._warn(f"Rate limited. Sleeping {retry_after}s...")
                        time.sleep(retry_after)
                        continue
                    return result
                
                return result
                
            except requests.exceptions.RequestException as e:
                self._error(f"Request failed: {e}")
                return None

    def _paginate(self, method: str, key: str, params: Optional[Dict] = None) -> List[Dict]:
        """Paginate through Slack API results."""
        results = []
        cursor = ''
        base_params = params or {}
        
        while True:
            call_params = {**base_params, 'limit': MAX_RESULTS_PER_PAGE}
            if cursor:
                call_params['cursor'] = cursor
            
            response = self._api_call(method, params=call_params)
            
            if not response or not response.get('ok'):
                break
            
            if key in response:
                results.extend(response[key])
            
            cursor = response.get('response_metadata', {}).get('next_cursor', '')
            if not cursor:
                break
        
        return results

    def _info(self, msg: str):
        print(termcolor.colored(f"[*] {msg}", "blue"))

    def _success(self, msg: str):
        print(termcolor.colored(f"[+] {msg}", "green"))

    def _warn(self, msg: str):
        print(termcolor.colored(f"[!] {msg}", "yellow"))

    def _error(self, msg: str):
        print(termcolor.colored(f"[-] {msg}", "red"))

    def _highlight(self, msg: str):
        print(termcolor.colored(f"[★] {msg}", "magenta"))

    def _save_json(self, filename: str, data: Any):
        """Save data to JSON file."""
        if not self.output_dir:
            return
        
        filepath = pathlib.Path(self.output_dir) / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        if self.verbose:
            self._info(f"Saved: {filepath}")

    def test_auth(self) -> bool:
        """Test token validity and get auth info."""
        self._info("Testing bot token...")
        
        response = self._api_call('auth.test')
        
        if not response:
            self._error("Failed to connect to Slack API")
            return False
        
        if not response.get('ok'):
            self._error(f"Token invalid: {response.get('error', 'unknown')}")
            return False
        
        self.bot_info = response
        self.data['auth'] = response
        
        # Extract scopes from response headers aren't available, try another way
        self._success(f"Token valid!")
        self._info(f"  Bot User ID: {response.get('user_id', 'N/A')}")
        self._info(f"  Bot User: {response.get('user', 'N/A')}")
        self._info(f"  Team: {response.get('team', 'N/A')}")
        self._info(f"  Team ID: {response.get('team_id', 'N/A')}")
        self._info(f"  URL: {response.get('url', 'N/A')}")
        self._info(f"  Enterprise ID: {response.get('enterprise_id', 'None')}")
        self._info(f"  Is Enterprise Install: {response.get('is_enterprise_install', False)}")
        
        # Set up output directory if not provided
        if not self.output_dir:
            team_name = response.get('team', 'unknown').replace(' ', '_')
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.output_dir = f"bot_enum_{team_name}_{timestamp}"
        
        pathlib.Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self._save_json('auth_info.json', response)
        
        return True

    def enum_team_info(self):
        """Get workspace/team information."""
        self._info("Enumerating team info...")
        
        response = self._api_call('team.info')
        
        if response and response.get('ok'):
            team = response.get('team', {})
            self.team_info = team
            self.data['team'] = team
            
            self._success(f"Team Info:")
            self._info(f"  Name: {team.get('name', 'N/A')}")
            self._info(f"  Domain: {team.get('domain', 'N/A')}.slack.com")
            self._info(f"  Email Domain: {team.get('email_domain', 'N/A')}")
            self._info(f"  Enterprise ID: {team.get('enterprise_id', 'None')}")
            self._info(f"  Enterprise Name: {team.get('enterprise_name', 'None')}")
            
            # Check for interesting settings
            if team.get('icon', {}).get('image_original'):
                self._info(f"  Icon: {team.get('icon', {}).get('image_original')}")
            
            self._save_json('team_info.json', team)
        else:
            self._warn(f"Cannot access team.info: {response.get('error', 'unknown') if response else 'no response'}")

    def enum_users(self):
        """Enumerate all users in the workspace."""
        self._info("Enumerating users...")
        
        users = self._paginate('users.list', 'members')
        
        if users:
            self.data['users'] = users
            
            # Stats
            active_users = [u for u in users if not u.get('deleted')]
            admins = [u for u in users if u.get('is_admin')]
            owners = [u for u in users if u.get('is_owner')]
            bots = [u for u in users if u.get('is_bot')]
            
            self._success(f"Found {len(users)} total users:")
            self._info(f"  Active: {len(active_users)}")
            self._info(f"  Admins: {len(admins)}")
            self._info(f"  Owners: {len(owners)}")
            self._info(f"  Bots: {len(bots)}")
            
            if admins:
                self._highlight("Admin users found:")
                for admin in admins[:10]:  # Show first 10
                    profile = admin.get('profile', {})
                    email = profile.get('email', 'no email')
                    self._info(f"    - {admin.get('name', 'N/A')} ({admin.get('real_name', 'N/A')}) - {email}")
                if len(admins) > 10:
                    self._info(f"    ... and {len(admins) - 10} more")
            
            if owners:
                self._highlight("Workspace owners found:")
                for owner in owners:
                    profile = owner.get('profile', {})
                    email = profile.get('email', 'no email')
                    self._info(f"    - {owner.get('name', 'N/A')} ({owner.get('real_name', 'N/A')}) - {email}")
            
            self._save_json('users.json', users)
            
            # Also create a condensed user list
            user_summary = []
            for u in users:
                profile = u.get('profile', {})
                user_summary.append({
                    'id': u.get('id'),
                    'name': u.get('name'),
                    'real_name': u.get('real_name'),
                    'email': profile.get('email'),
                    'title': profile.get('title'),
                    'is_admin': u.get('is_admin'),
                    'is_owner': u.get('is_owner'),
                    'is_bot': u.get('is_bot'),
                    'deleted': u.get('deleted'),
                    'is_restricted': u.get('is_restricted'),
                    'is_ultra_restricted': u.get('is_ultra_restricted')
                })
            self._save_json('users_summary.json', user_summary)
        else:
            self._warn("Cannot enumerate users or no users found")

    def enum_channels(self):
        """Enumerate all accessible channels."""
        self._info("Enumerating channels...")
        
        # Get public channels
        public_channels = self._paginate('conversations.list', 'channels', 
                                          params={'types': 'public_channel'})
        
        # Get private channels the bot is in
        private_channels = self._paginate('conversations.list', 'channels',
                                           params={'types': 'private_channel'})
        
        # Get IMs (direct messages with bot)
        ims = self._paginate('conversations.list', 'channels',
                             params={'types': 'im'})
        
        # Get MPIMs (group DMs)
        mpims = self._paginate('conversations.list', 'channels',
                               params={'types': 'mpim'})
        
        all_channels = {
            'public': public_channels,
            'private': private_channels,
            'im': ims,
            'mpim': mpims
        }
        
        self.data['channels'] = all_channels
        
        self._success(f"Channels found:")
        self._info(f"  Public channels: {len(public_channels)}")
        self._info(f"  Private channels: {len(private_channels)}")
        self._info(f"  Direct messages: {len(ims)}")
        self._info(f"  Group DMs: {len(mpims)}")
        
        # Bot membership
        bot_member_channels = [c for c in public_channels + private_channels if c.get('is_member')]
        if bot_member_channels:
            self._highlight(f"Bot is a member of {len(bot_member_channels)} channels:")
            for ch in bot_member_channels[:15]:
                ch_type = "🔒" if ch.get('is_private') else "📢"
                members = ch.get('num_members', '?')
                self._info(f"    {ch_type} #{ch.get('name', 'unnamed')} ({members} members)")
            if len(bot_member_channels) > 15:
                self._info(f"    ... and {len(bot_member_channels) - 15} more")
        
        self._save_json('channels.json', all_channels)
        
        # Create channel summary
        channel_summary = []
        for ch_list in [public_channels, private_channels]:
            for ch in ch_list:
                channel_summary.append({
                    'id': ch.get('id'),
                    'name': ch.get('name'),
                    'is_private': ch.get('is_private'),
                    'is_member': ch.get('is_member'),
                    'num_members': ch.get('num_members'),
                    'topic': ch.get('topic', {}).get('value', ''),
                    'purpose': ch.get('purpose', {}).get('value', ''),
                    'created': ch.get('created'),
                    'creator': ch.get('creator')
                })
        self._save_json('channels_summary.json', channel_summary)
        
        return bot_member_channels

    def enum_channel_history(self, channels: List[Dict], max_messages: int = 100):
        """Enumerate message history from channels the bot has access to."""
        self._info(f"Enumerating channel history (max {max_messages} messages per channel)...")
        
        conversations = {}
        
        for channel in channels[:20]:  # Limit to first 20 channels
            channel_id = channel.get('id')
            channel_name = channel.get('name', channel_id)
            
            response = self._api_call('conversations.history', params={
                'channel': channel_id,
                'limit': min(max_messages, 100)
            })
            
            if response and response.get('ok'):
                messages = response.get('messages', [])
                if messages:
                    conversations[channel_name] = {
                        'channel_id': channel_id,
                        'message_count': len(messages),
                        'messages': messages
                    }
                    self._info(f"  #{channel_name}: {len(messages)} messages")
            else:
                error = response.get('error', 'unknown') if response else 'no response'
                if self.verbose:
                    self._warn(f"  #{channel_name}: cannot access ({error})")
        
        self.data['conversations'] = conversations
        
        if conversations:
            self._success(f"Retrieved history from {len(conversations)} channels")
            self._save_json('conversations.json', conversations)
        
        return conversations

    def enum_files(self):
        """Enumerate accessible files."""
        self._info("Enumerating files...")
        
        files = self._paginate('files.list', 'files')
        
        if files:
            self.data['files'] = files
            
            # Stats by type
            file_types = {}
            total_size = 0
            for f in files:
                ftype = f.get('filetype', 'unknown')
                file_types[ftype] = file_types.get(ftype, 0) + 1
                total_size += f.get('size', 0)
            
            self._success(f"Found {len(files)} files ({total_size / 1024 / 1024:.2f} MB total)")
            
            if self.verbose:
                self._info("  File types:")
                for ftype, count in sorted(file_types.items(), key=lambda x: -x[1])[:10]:
                    self._info(f"    {ftype}: {count}")
            
            self._save_json('files.json', files)
            
            # Create file summary
            file_summary = []
            for f in files:
                file_summary.append({
                    'id': f.get('id'),
                    'name': f.get('name'),
                    'title': f.get('title'),
                    'filetype': f.get('filetype'),
                    'size': f.get('size'),
                    'user': f.get('user'),
                    'created': f.get('created'),
                    'url_private': f.get('url_private'),
                    'url_private_download': f.get('url_private_download'),
                    'channels': f.get('channels', []),
                    'is_external': f.get('is_external')
                })
            self._save_json('files_summary.json', file_summary)
        else:
            self._warn("Cannot enumerate files or no files found")

    def enum_emoji(self):
        """Enumerate custom emoji."""
        self._info("Enumerating custom emoji...")
        
        response = self._api_call('emoji.list')
        
        if response and response.get('ok'):
            emoji = response.get('emoji', {})
            self.data['emoji'] = emoji
            
            self._success(f"Found {len(emoji)} custom emoji")
            self._save_json('emoji.json', emoji)
        else:
            error = response.get('error', 'unknown') if response else 'no response'
            self._warn(f"Cannot enumerate emoji: {error}")

    def enum_usergroups(self):
        """Enumerate user groups (Slack Connect, etc.)."""
        self._info("Enumerating user groups...")
        
        response = self._api_call('usergroups.list', params={'include_users': True})
        
        if response and response.get('ok'):
            groups = response.get('usergroups', [])
            self.data['usergroups'] = groups
            
            if groups:
                self._success(f"Found {len(groups)} user groups:")
                for g in groups:
                    self._info(f"  @{g.get('handle', 'unnamed')} - {g.get('name', 'N/A')} ({len(g.get('users', []))} members)")
                
                self._save_json('usergroups.json', groups)
            else:
                self._info("No user groups found")
        else:
            error = response.get('error', 'unknown') if response else 'no response'
            self._warn(f"Cannot enumerate user groups: {error}")

    def enum_bots(self):
        """Enumerate bots in the workspace."""
        self._info("Enumerating bots...")
        
        # Get bots from users list
        if self.data['users']:
            bots = [u for u in self.data['users'] if u.get('is_bot')]
            self.data['bots'] = bots
            
            if bots:
                self._success(f"Found {len(bots)} bots:")
                for bot in bots[:10]:
                    self._info(f"  - {bot.get('name', 'unnamed')} ({bot.get('id', 'N/A')})")
                if len(bots) > 10:
                    self._info(f"  ... and {len(bots) - 10} more")
                
                self._save_json('bots.json', bots)
        else:
            self._warn("Run enum_users first to get bot info")

    def enum_pins(self, channels: List[Dict]):
        """Enumerate pinned messages in accessible channels."""
        self._info("Enumerating pinned messages...")
        
        all_pins = {}
        
        for channel in channels:
            channel_id = channel.get('id')
            channel_name = channel.get('name', channel_id)
            
            response = self._api_call('pins.list', params={'channel': channel_id})
            
            if response and response.get('ok'):
                items = response.get('items', [])
                if items:
                    all_pins[channel_name] = items
                    self._info(f"  #{channel_name}: {len(items)} pins")
        
        self.data['pins'] = all_pins
        
        if all_pins:
            total_pins = sum(len(p) for p in all_pins.values())
            self._success(f"Found {total_pins} pinned items across {len(all_pins)} channels")
            self._save_json('pins.json', all_pins)
        else:
            self._info("No pinned messages found")

    def enum_bookmarks(self, channels: List[Dict]):
        """Enumerate bookmarks in accessible channels."""
        self._info("Enumerating channel bookmarks...")
        
        all_bookmarks = {}
        
        for channel in channels:
            channel_id = channel.get('id')
            channel_name = channel.get('name', channel_id)
            
            response = self._api_call('bookmarks.list', params={'channel_id': channel_id})
            
            if response and response.get('ok'):
                bookmarks = response.get('bookmarks', [])
                if bookmarks:
                    all_bookmarks[channel_name] = bookmarks
                    self._info(f"  #{channel_name}: {len(bookmarks)} bookmarks")
        
        self.data['bookmarks'] = all_bookmarks
        
        if all_bookmarks:
            total = sum(len(b) for b in all_bookmarks.values())
            self._success(f"Found {total} bookmarks across {len(all_bookmarks)} channels")
            self._save_json('bookmarks.json', all_bookmarks)
        else:
            self._info("No bookmarks found")

    def check_admin_apis(self):
        """Check if we have access to admin APIs (Enterprise Grid)."""
        self._info("Checking admin API access...")
        
        admin_methods = [
            ('admin.apps.approved.list', 'Approved apps'),
            ('admin.apps.restricted.list', 'Restricted apps'),
            ('admin.conversations.getConversationPrefs', 'Conversation prefs'),
            ('admin.emoji.list', 'Admin emoji'),
            ('admin.inviteRequests.list', 'Invite requests'),
            ('admin.teams.list', 'Teams in enterprise'),
            ('admin.users.list', 'Admin user list'),
        ]
        
        admin_access = {}
        has_any_admin = False
        
        for method, description in admin_methods:
            response = self._api_call(method)
            if response and response.get('ok'):
                has_any_admin = True
                admin_access[method] = True
                self._highlight(f"  ✓ {description} ({method})")
            else:
                admin_access[method] = False
                if self.verbose:
                    error = response.get('error', 'unknown') if response else 'no response'
                    self._info(f"  ✗ {description}: {error}")
        
        if has_any_admin:
            self._highlight("Admin API access detected!")
            self._save_json('admin_access.json', admin_access)
        else:
            self._info("No admin API access")
        
        return admin_access

    def check_scopes(self):
        """Attempt to determine token scopes by testing various APIs."""
        self._info("Probing token capabilities...")
        
        scope_tests = [
            ('channels:read', 'conversations.list', {'types': 'public_channel', 'limit': 1}),
            ('groups:read', 'conversations.list', {'types': 'private_channel', 'limit': 1}),
            ('im:read', 'conversations.list', {'types': 'im', 'limit': 1}),
            ('mpim:read', 'conversations.list', {'types': 'mpim', 'limit': 1}),
            ('users:read', 'users.list', {'limit': 1}),
            ('users:read.email', 'users.list', {'limit': 1}),  # Check if emails visible
            ('team:read', 'team.info', {}),
            ('files:read', 'files.list', {'count': 1}),
            ('emoji:read', 'emoji.list', {}),
            ('usergroups:read', 'usergroups.list', {}),
            ('search:read', 'search.messages', {'query': 'test', 'count': 1}),
            ('pins:read', 'pins.list', {'channel': 'C00000000'}),  # Will fail but shows if scope exists
            ('bookmarks:read', 'bookmarks.list', {'channel_id': 'C00000000'}),
        ]
        
        detected_scopes = []
        
        for scope, method, params in scope_tests:
            response = self._api_call(method, params=params)
            if response:
                if response.get('ok'):
                    detected_scopes.append(scope)
                    self._info(f"  ✓ {scope}")
                elif response.get('error') == 'missing_scope':
                    if self.verbose:
                        self._info(f"  ✗ {scope} (missing)")
                elif response.get('error') == 'channel_not_found':
                    # For methods that need a valid channel, we can't tell
                    detected_scopes.append(f"{scope} (likely)")
                    self._info(f"  ? {scope} (likely - needs valid channel)")
        
        self.scopes = detected_scopes
        self._save_json('detected_scopes.json', detected_scopes)
        
        return detected_scopes

    def search_messages(self, query: str):
        """Search messages (if search:read scope is available)."""
        self._info(f"Searching messages for: {query}")
        
        response = self._api_call('search.messages', params={
            'query': query,
            'count': 100
        })
        
        if response and response.get('ok'):
            messages = response.get('messages', {})
            total = messages.get('total', 0)
            matches = messages.get('matches', [])
            
            self._success(f"Found {total} messages matching '{query}'")
            
            if matches:
                self._save_json(f'search_{query.replace(" ", "_")}.json', matches)
            
            return matches
        else:
            error = response.get('error', 'unknown') if response else 'no response'
            self._warn(f"Search failed: {error}")
            return []

    def run_full_enumeration(self, include_history: bool = True, search_terms: List[str] = None):
        """Run full enumeration."""
        print(termcolor.colored("\n" + "=" * 60, "cyan"))
        print(termcolor.colored("  SlackBotEnum - Slack Bot Token Enumeration", "cyan"))
        print(termcolor.colored("=" * 60 + "\n", "cyan"))
        
        # 1. Test authentication
        if not self.test_auth():
            return False
        
        print()
        
        # 2. Check token capabilities
        self.check_scopes()
        print()
        
        # 3. Team info
        self.enum_team_info()
        print()
        
        # 4. Users
        self.enum_users()
        print()
        
        # 5. Channels
        member_channels = self.enum_channels()
        print()
        
        # 6. Channel history (if bot is member of channels)
        if include_history and member_channels:
            self.enum_channel_history(member_channels)
            print()
            
            # 6a. Pins
            self.enum_pins(member_channels)
            print()
            
            # 6b. Bookmarks
            self.enum_bookmarks(member_channels)
            print()
        
        # 7. Files
        self.enum_files()
        print()
        
        # 8. Emoji
        self.enum_emoji()
        print()
        
        # 9. User groups
        self.enum_usergroups()
        print()
        
        # 10. Bots
        self.enum_bots()
        print()
        
        # 11. Admin API check
        self.check_admin_apis()
        print()
        
        # 12. Search for interesting terms
        if search_terms:
            self._info("Running keyword searches...")
            for term in search_terms:
                self.search_messages(term)
            print()
        
        # Summary
        print(termcolor.colored("=" * 60, "cyan"))
        print(termcolor.colored("  Enumeration Complete!", "cyan"))
        print(termcolor.colored("=" * 60, "cyan"))
        
        self._success(f"Output directory: {self.output_dir}")
        self._info(f"  Users: {len(self.data['users'])}")
        self._info(f"  Public channels: {len(self.data['channels'].get('public', []))}")
        self._info(f"  Private channels: {len(self.data['channels'].get('private', []))}")
        self._info(f"  Files: {len(self.data['files'])}")
        self._info(f"  Custom emoji: {len(self.data['emoji'])}")
        self._info(f"  User groups: {len(self.data['usergroups'])}")
        
        # Save full data dump
        self._save_json('full_enumeration.json', self.data)
        
        return True


def main():
    colorama.init()
    
    parser = argparse.ArgumentParser(
        description="SlackBotEnum - Enumerate Slack workspace data using a bot token (xoxb-)"
    )
    
    parser.add_argument(
        '--token', '-t',
        type=str,
        required=True,
        help='Slack bot token (starts with xoxb-)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        required=False,
        help='Output directory (default: auto-generated)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--no-history',
        action='store_true',
        help='Skip channel history enumeration'
    )
    
    parser.add_argument(
        '--search', '-s',
        type=str,
        nargs='*',
        help='Search terms to look for (e.g., "password" "api key" "secret")'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick mode - only enumerate basic info (auth, team, channels)'
    )
    
    args = parser.parse_args()
    
    # Validate token format
    if not args.token.startswith('xoxb-'):
        print(termcolor.colored("[!] Warning: Token does not start with 'xoxb-'. This tool is designed for bot tokens.", "yellow"))
        print(termcolor.colored("    User tokens (xoxp-) and client tokens (xoxc-) may work but with different results.", "yellow"))
    
    # Default search terms for security-relevant content
    default_search = ['password', 'secret', 'api key', 'credential', 'token', 'private key']
    search_terms = args.search if args.search else (None if args.quick else default_search)
    
    enumerator = SlackBotEnumerator(
        token=args.token,
        output_dir=args.output,
        verbose=args.verbose
    )
    
    if args.quick:
        # Quick mode - just basic enumeration
        if not enumerator.test_auth():
            sys.exit(1)
        enumerator.check_scopes()
        enumerator.enum_team_info()
        enumerator.enum_channels()
        print(termcolor.colored(f"\n[+] Quick enumeration complete. Output: {enumerator.output_dir}", "green"))
    else:
        # Full enumeration
        success = enumerator.run_full_enumeration(
            include_history=not args.no_history,
            search_terms=search_terms
        )
        
        if not success:
            sys.exit(1)


if __name__ == '__main__':
    main()

