import { getEmailAuthController } from './emailAuthRuntime'
export { PasswordRecoveryError } from './emailAuth'

export async function requestPasswordReset(email: string): Promise<void> {
  return getEmailAuthController().requestReset(email)
}

export async function updatePassword(newPassword: string): Promise<void> {
  return getEmailAuthController().updatePassword(newPassword)
}
