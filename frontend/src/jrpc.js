import simple_jsonrpc from 'simple-jsonrpc-js';

const socketURL = 'ws://localhost:8000';

let rpc;

export const RPC = () => {
    if (rpc) return rpc;

    const socket = new WebSocket(socketURL);

    var jrpc = new simple_jsonrpc();

    socket.onmessage = function (event) {
        console.log('got data', event.data);
        jrpc.messageHandler(event.data);
    };

    jrpc.toStream = function (_msg) {
        socket.send(_msg);
    };

    socket.onerror = function (error) {
        console.error('Error: ' + error.message);
    };

    socket.onclose = function (event) {
        if (event.wasClean) {
            console.info('Connection close was clean');
        } else {
            console.error('Connection suddenly close');
        }
        console.info('close code : ' + event.code + ' reason: ' + event.reason);
    };

    return new Promise((resolve, reject) => {
        socket.onopen = () => {
            rpc = jrpc;
            resolve(jrpc);
        };
    });
};

export const rpcEcho = async (text) => {
    let rpc = await RPC();
    const response = await rpc.call('echo', [text]);

    console.log(JSON.stringify(response));
    return response;
}