export type AuthSession = {
  accessToken: string
  expiresIn: number
  userId: string
  username: string
}

export type AuthPayload = {
  username: string
  password: string
}

export type TokenResponse = {
  access_token: string
  token_type: "bearer"
  expires_in: number
  user_id: string
  username: string
}
