import {
  AccessToken,
  AccessTokenOptions,
  VideoGrant,
} from "livekit-server-sdk";
import { NextRequest, NextResponse } from "next/server";

// NOTE: you are expected to define the following environment variables in `.env.local`:
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;

// don't cache the results
export const revalidate = 0;

export interface ConnectionDetails {
  participantToken: string;
  serverUrl: string;
}

export interface RequestBody {
  userName: string;
  agentId: string;
  userId: string;
  uploadedFile?: {
    content: string;
    filename: string;
  } | null;
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    
    // Forward the request to your Railway backend
    const response = await fetch('https://talkwdocs-production.up.railway.app/connection-details', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      throw new Error(`Backend responded with ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Connection details error:', error);
    return NextResponse.json({ error: 'Failed to get connection details' }, { status: 500 });
  }
}

async function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string
): Promise<string> {
  const at = new AccessToken(API_KEY!, API_SECRET!, {
    ...userInfo,
    ttl: "15m",
  });

  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };
  at.addGrant(grant);
  
  return at.toJwt();
}
