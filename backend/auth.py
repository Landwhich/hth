import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from dotenv import load_dotenv

load_dotenv()

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_API_AUDIENCE = os.getenv("AUTH0_API_AUDIENCE")
AUTH0_ALGORITHMS = ["RS256"]

token_auth_scheme = HTTPBearer()

def verify_token(token: HTTPAuthorizationCredentials = Depends(token_auth_scheme)):
    if not AUTH0_DOMAIN or not AUTH0_API_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 domain or API audience is not configured."
        )
    
    jwks_url = f'https://{AUTH0_DOMAIN}/.well-known/jwks.json'
    
    import ssl
    import certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    jwks_client = PyJWKClient(jwks_url, ssl_context=ssl_context)

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token.credentials)
        payload = jwt.decode(
            token.credentials,
            signing_key.key,
            algorithms=AUTH0_ALGORITHMS,
            audience=AUTH0_API_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/"
        )
        return payload
    except jwt.exceptions.PyJWKClientError as error:
        print(f"PyJWKClientError: {repr(error)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error))
    except jwt.exceptions.DecodeError as error:
        print(f"DecodeError: {repr(error)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error))
    except jwt.ExpiredSignatureError:
        print("ExpiredSignatureError")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token signature has expired")
    except Exception as e:
        print(f"JWT Validation Error: {repr(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token validation failed: {str(e)}")
