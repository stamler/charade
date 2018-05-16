# middleware
# Basic Azure ActiveDirectory JWT Token Validation

import jwt
import falcon
import time
import config
import requests
import logging
from cryptography.x509 import load_pem_x509_certificate as load_cert
from cryptography.hazmat.backends import default_backend

class AzureADTokenValidator(object):
    def __init__(self,tenant_name,app_id,refresh_interval=3600):
        self.app_id = app_id
        self.tenant_name = tenant_name
        self.log = logging.getLogger(__name__)
        self.log.addHandler(logging.NullHandler())

        # Don't validate OPTIONS requests for preflighting
        self.exempt_methods = ['OPTIONS']

        # Time in seconds to keep cached keys from Microsoft
        self.key_refresh_interval = refresh_interval

        self._load_certificates()

    # Get the token signing keys from Microsoft and store them in self.keys,
    # a dict with 'kid' as the key and cert as the value
    def _load_certificates(self):
        self.last_refresh = int(time.time())
        res = requests.get('https://login.microsoftonline.com/' +
                           self.tenant_name + '/.well-known/openid-configuration')
        res = requests.get(res.json()['jwks_uri'])
        self.keys = {}
        for key in res.json()['keys']:
            x5c = key['x5c']
            cert = ''.join([ '-----BEGIN CERTIFICATE-----\n', x5c[0],
                                            '\n-----END CERTIFICATE-----\n' ])
            public_key = load_cert(cert.encode(), default_backend()).public_key()
            self.keys[key['kid']] = public_key

    def validate_token(self, access_token):

        # reload the keys if they're stale
        if (int(time.time()) - self.last_refresh > self.key_refresh_interval):
            self._load_certificates()

        if(access_token):
            token_header = jwt.get_unverified_header(access_token)

            if (token_header['kid'] in self.keys):
                public_key = self.keys[token_header['kid']]

                # The key id is one we have, continue the validation
                # Validate the token against the public_key and the app_id. If it
                # decodes here then we can respect the claims it contains
                try:
                    decoded = jwt.decode(access_token, public_key,
                                         algorithms = token_header['alg'],
                                           audience = self.app_id)
                    expiry = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(decoded['exp']))
                    self.log.debug("Token is valid until {}".format(expiry))
                    return decoded
                except Exception as e:
                    self.log.warning('Token failed validation {}'.format(e))
                    raise falcon.HTTPUnauthorized('Authentication Required',
                                    'Provided token is not valid.', None)
            else:
                # The key in the token_header is not in our list of valid keys
                # There's no way to validate the token so deny access
                self.log.debug('Provided token is signed by an unrecognized authority')
                raise falcon.HTTPUnauthorized('Authentication Required',
                                'Provided token is signed by an unrecognized authority.', None)
        else:
            # No token provided, deny access
            self.log.debug('No token provided, denying access')
            raise falcon.HTTPUnauthorized('Authentication Required',
                            'Please provide a valid token.', None)

    def process_resource(self, req, resp, resource, params):
        #self.log.debug("request: {}".format(req))
        self.log.debug("request.headers: {}".format(req.headers))

        if( req.method in self.exempt_methods):
            return

        #BYPASS AUTH FOR POST to RawLogins ***TEMPORARY FOR TESTING****
        if( req.method == 'POST' and req.path == '/RawLogins'):
            return

        if (req.get_header('Authorization')):
            token = req.get_header('Authorization').partition('Bearer ')[2]
            claims = self.validate_token(token)
        else:
            raise falcon.HTTPUnauthorized('Authentication Required',
                            'Please provide a valid token.', None)

        # Do anything we need to do with the claims
        #params['jwt_claims'] = {}
        #for claim in claims:
        #    params['jwt_claims'][claim] = claims[claim]

class CORSComponent(object):
    def process_response(self, req, resp, resource, req_succeeded):
        resp.set_header('Access-Control-Allow-Origin', '*')

        if (req_succeeded
            and req.method == 'OPTIONS'
            and req.get_header('Access-Control-Request-Method')
        ):

            allow = resp.get_header('Allow')
            resp.delete_header('Allow')

            allow_headers = req.get_header(
                'Access-Control-Request-Headers',
                default='*'
            )

            resp.set_headers((
                ('Access-Control-Allow-Methods', allow),
                ('Access-Control-Allow-Headers', allow_headers),
                ('Access-Control-Max-Age', '86400'),  # 24 hours
            ))

# https://developers.google.com/web/fundamentals/performance/optimizing-content-efficiency/http-caching
class CacheController(object):
    def process_response(self, req, resp, resource, req_succeeded):
        safe_methods = ['GET', 'OPTIONS', 'HEAD']
        if (req_succeeded and req.method in safe_methods):
            resp.cache_control = ['max-age=60']
