// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// react-router v7 needs TextEncoder, which CRA's jsdom test environment doesn't provide.
import { TextDecoder, TextEncoder } from 'util';
Object.assign(global, { TextEncoder, TextDecoder });
