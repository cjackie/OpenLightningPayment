import { useState, useEffect, useReducer, useContext } from 'react';
import { StoreContext, types} from '../store';
import { rpcEcho } from '../jrpc';

export const Website = () => {
    const { store, dispatch } = useContext(StoreContext);
    const [ someText, setSomeText ] = useState('');
    const [ echo, setEcho ] = useState('');

    useEffect(() => {
        if (!someText !== '') {
            setSomeText('some text');
        }
        if (!store.dummyText) {
            dispatch({
                type: types.SET_DUMMY_TEXT,
                dummyText: 'some dummpy Text'
            });
        }

        // Passing async function to useEffect is not allowed for some reason. This is a workaround.
        (async () => {
            let text = await rpcEcho("echo text 1939");
            setEcho(text);
        })();
    }, [someText]);

    return <div>
        Hello {someText}
        <br/>
        {store.dummyText}
        <br/>
        {echo}
    </div>
}