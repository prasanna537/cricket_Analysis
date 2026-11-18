import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import TopBar from "./TopBar";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const serif = Source_Serif_4({ subsets: ["latin"], variable: "--font-serif", display: "swap" });

export const metadata: Metadata = {
  title: "Most Reliable Players Under Pressure",
  description: "SuperRR Selector Season 2, Round 1: the batters and bowlers who hold up best in high-pressure moments.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body>
        <TopBar />
        {children}
      </body>
    </html>
  );
}
