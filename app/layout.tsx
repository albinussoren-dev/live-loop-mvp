import './globals.css';
import type { ReactNode } from 'react';
export const metadata={title:'LoopLive — YouTube 24/7 Live',description:'Cloud live-loop dashboard MVP'};
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en"><body>{children}</body></html>}