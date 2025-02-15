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

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as RequestBody;
    const roomName = `room_${Math.random().toString(36).substring(7)}`;

    if (!API_KEY || !API_SECRET) {
      throw new Error("LiveKit API credentials are not configured");
    }

    // Create a participant token with the uploaded file in metadata
    const token = await createParticipantToken(
      {
        identity: body.userId,
        name: body.userName,
        metadata: body.uploadedFile 
          ? JSON.stringify({
              uploadedFile: {
                content: body.uploadedFile.content,
                filename: body.uploadedFile.filename,
              },
            })
          : undefined,
      },
      roomName
    );

    if (!LIVEKIT_URL) {
      throw new Error("LIVEKIT_URL is not defined");
    }

    const response: ConnectionDetails = {
      participantToken: token,
      serverUrl: LIVEKIT_URL,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Error creating connection details:', error);
    return NextResponse.json(
      { error: 'Failed to create connection details' },
      { status: 500 }
    );
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
