import { useReducer } from 'react';
import { initialValue, reducer, StoreContext } from '../store';
import { Website } from './Website';

export const App = () => {
    const [store, dispatch] = useReducer(reducer, initialValue);

    return (
        <div className="App">
            <StoreContext.Provider value={{ store, dispatch }}>
                <Website />
            </StoreContext.Provider>
        </div>
    );
}

