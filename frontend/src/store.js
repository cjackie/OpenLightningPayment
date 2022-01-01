import { createContext } from 'react';

/**
 * @user 
 *  User {
 *      jwt_token: str
 *      refresh_token: Str
 *      expired_on: int
 *  }
 * @invoice
 *  Invoice {
 *      invoiceId: int 
 *      status: str
 *      encodedInvoice: str
 *      createdAt: int
 *      amountRequested: int
 *      exchangeRate: int
 *      expiredAt: int
 *  }
 */
export const initialValue = {
    user: null,
    invoice: null,
    dummyText: '',
};

export const types = {
    SET_INVOICE: 'SET_INVOICE',
    SET_USER: 'SET_USER',
    SET_DUMMY_TEXT: 'SET_DUMMY_TEXT'
};

export const reducer = (state, action) => {
    let result = { ...state };

    switch (action.type) {
        case types.SET_INVOICE:
            result = { ...state, loginURL: action.invoice };
            break;
        case types.SET_USER:
            result = { ...state, user: action.user };
            break;
        case types.SET_DUMMY_TEXT:
            result = { ...state, dummyText: action.dummyText};
        default:
            break;
    }

    console.log('\nStore update:', result);
    return result;
};

export const StoreContext = createContext(initialValue);