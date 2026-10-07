"""Small Chat Completions client using Python's standard library."""
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from ai_features import AIError, MAX_RESULT

DEFAULT_CONFIG = {'base_url': 'https://api.openai.com/v1', 'model': '',
                  'max_tokens': 4096, 'timeout': 60}


def endpoint_for(base_url):
    if not isinstance(base_url, str) or not base_url.strip() or len(base_url) > 2000:
        raise AIError('Enter an API base URL.')
    value = base_url.strip().rstrip('/')
    if any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise AIError('The API address contains invalid characters.')
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise AIError('Invalid API address.') from exc
    if not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise AIError('Use an API URL without embedded credentials, query parameters or fragments.')
    local = parsed.hostname.lower() in ('localhost', '127.0.0.1', '::1')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and local):
        raise AIError('Use HTTPS for remote APIs. HTTP is allowed only for localhost.')
    if port is not None and not 1 <= port <= 65535:
        raise AIError('Invalid API address.')
    if parsed.path.endswith('/chat/completions'):
        return value
    return value + '/chat/completions'


def public_config(config, require_model=True):
    if not isinstance(config, dict):
        raise AIError('Invalid AI settings.')
    result = dict(DEFAULT_CONFIG)
    for key in DEFAULT_CONFIG:
        if key in config:
            result[key] = config[key]
    endpoint_for(result['base_url'])
    result['base_url'] = result['base_url'].strip().rstrip('/')
    model = result['model']
    if not isinstance(model, str) or len(model) > 200 or any(ord(c) < 32 for c in model):
        raise AIError('Enter a valid model name supplied by your provider.')
    model = model.strip()
    if require_model and not model:
        raise AIError('Enter a model name supplied by your provider.')
    result['model'] = model
    for key, minimum, maximum in [('max_tokens', 128, 16384), ('timeout', 5, 180)]:
        value = result[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise AIError('Invalid output limit or timeout.')
    # Only these four public fields are returned. Never persist credentials.
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_response(data):
    if not isinstance(data, dict):
        raise AIError('The API returned an unexpected response format.')
    choices = data.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise AIError('The API did not return a text completion.')
    choice = choices[0]
    reason = choice.get('finish_reason')
    if reason == 'length':
        raise AIError('The response was cut off. Increase the output limit or shorten the input and retry.')
    if reason in ('content_filter', 'tool_calls', 'function_call'):
        raise AIError('The model did not return usable text for this task.')
    message = choice.get('message')
    if not isinstance(message, dict) or message.get('tool_calls') or message.get('function_call'):
        raise AIError('The model did not return usable text for this task.')
    if message.get('refusal'):
        raise AIError('The model declined this request.')
    content = message.get('content')
    if isinstance(content, list):
        content = ''.join(part.get('text', '') for part in content
                          if isinstance(part, dict) and part.get('type') == 'text' and isinstance(part.get('text'), str))
    if not isinstance(content, str) or not content.strip():
        raise AIError('The API returned no text. Check the model and output limit.')
    if any(0xd800 <= ord(c) <= 0xdfff for c in content):
        raise AIError('The API returned invalid Unicode text.')
    if len(content) > MAX_RESULT:
        raise AIError('The AI result is too large.')
    usage = data.get('usage', {})
    total = usage.get('total_tokens') if isinstance(usage, dict) else None
    if type(total) is not int or total < 0:
        total = None
    return {'text': content, 'total_tokens': total}


def complete(config, api_key, messages):
    config = public_config(config)
    endpoint = endpoint_for(config['base_url'])
    host = urllib.parse.urlsplit(endpoint).hostname.lower()
    if not isinstance(api_key, str) or '\n' in api_key or '\r' in api_key or len(api_key) > 10000:
        raise AIError('Invalid API key.')
    api_key = api_key.strip()
    if not api_key and host not in ('localhost', '127.0.0.1', '::1'):
        raise AIError('Enter your API key. It is used only for this app session.')
    if not isinstance(messages, list) or not messages:
        raise AIError('The AI request has no messages.')
    payload = {'model': config['model'], 'messages': messages, 'stream': False}
    token_field = 'max_completion_tokens' if host == 'api.openai.com' else 'max_tokens'
    payload[token_field] = config['max_tokens']
    if host == 'api.openai.com':
        payload['store'] = False
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(encoded) > 512_000:
        raise AIError('The AI request is too large.')
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
               'User-Agent': 'Typecraft/AI'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    request = urllib.request.Request(endpoint, data=encoded, headers=headers, method='POST')
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=config['timeout']) as response:
            raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise AIError('The API response is too large.')
        try:
            data = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise AIError('The API returned invalid JSON. Check the API address and compatibility.') from exc
        return parse_response(data)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code in (301, 302, 303, 307, 308):
            raise AIError('The API redirected the request. Enter the final API address; credentials were not forwarded.') from None
        errors = {401: 'Authentication failed. Check your API key.',
                  403: 'Access denied. Check your key permissions and model access.',
                  404: 'API endpoint or model not found. Check the address and model name.',
                  429: 'The API rate limit or quota was reached. Check your provider account.',
                  400: 'The API rejected the request. Check the model, endpoint and output limit.'}
        raise AIError(errors.get(code, 'The API returned HTTP {code}.').format(code=code)) from None
    except (TimeoutError, socket.timeout):
        raise AIError('The API request timed out. Check the connection or try a larger timeout.') from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise AIError('The API request timed out. Check the connection or try a larger timeout.') from None
        raise AIError('Could not reach the API. Check the address, network and TLS certificate.') from None
    except (OSError, ssl.SSLError, UnicodeError):
        raise AIError('Could not reach the API. Check the address, network and TLS certificate.') from None
