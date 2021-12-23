import time

JSONRPC_ERROR_CODE_PARSE_ERROR = -32700
JSONRPC_ERROR_CODE_INVALID_REQUEST = -32600
JSONRPC_ERROR_CODE_METHOD_NOT_FOUND = -32601
JSONRPC_ERROR_CODE_INVALID_PARAMS = -32602
JSONRPC_ERROR_CODE_INTERNAL_ERROR = -32603

class JsonRpcException(Exception):
    def __init__(self, error_message, code, message_to_client: str = ""):
        Exception.__init__(self, error_message)
        self.code = code
        # Surface to the client.
        self.message_to_client = message_to_client

class WebSocketSend():
    async def send(self, data:str):
        raise NotImplementedError("Must be implemented")

class JsonRpcRequest():
    def __init__(self, jsonrpc, method, params, id):
        self.jsonrpc = jsonrpc
        self.method = method
        self.params = params
        self.id = id

class JsonRpcHandler():
    def can_handle(request: JsonRpcRequest) -> bool: 
        raise NotImplementedError("")

    async def handle(request: JsonRpcRequest):
        raise NotImplementedError("")

class JsonRpcSession():
    '''
    global state per websocket
    '''
    def __init__(self):
        # Auth related. If not None, then account_id is the login user for the websocket.
        self.account_id = None
        self.exp = 0
    
    def check_auth(self):
        if not self.account_id or self.exp < int(time.time()):
            raise JsonRpcException("The remote is not authenticated", JSONRPC_ERROR_CODE_INVALID_REQUEST, "Please authenticate")


