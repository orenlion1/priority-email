# Push Notification Provider Options

## Recommendation

Use **AWS End User Messaging Push** as the preferred production push provider.

Why:

- AWS-native and fits the existing EKS, IRSA, Secrets Manager, CloudWatch, and CloudTrail deployment model.
- Low cost for this workload: AWS lists the first 1,000,000 push notifications per month at $0, then $0.000001 per push notification after that.
- Supports APNs for iOS and Firebase Cloud Messaging for Android.
- Avoids introducing another notification vendor into the production path.
- The service is the current AWS path for push notification features that were previously associated with Amazon Pinpoint.

Important caveat:

- Real mobile push still requires a receiving app or registered device token. For iOS, that means APNs credentials and typically an Apple Developer Program membership. For Android, that means FCM credentials. AWS simplifies the server-side send path, but it does not remove the need for platform push credentials.

## Provider Comparison

| Provider | Cost Profile | AWS Fit | Pros | Cons | Recommendation |
| --- | --- | --- | --- | --- | --- |
| AWS End User Messaging Push | First 1M/month free, then very low per-send cost | Excellent | AWS-native, supports APNs/FCM, CloudWatch and CloudTrail integration, good production fit | Requires APNs/FCM credentials and device token registration | Preferred production choice |
| Amazon SNS Mobile Push | Low-cost AWS-native messaging, with SNS free tier and low per-million delivery cost | Very good | Simple AWS-native pub/sub model, mature service, cheap | Less purpose-built than End User Messaging Push for mobile engagement resources | Consider if implementation is simpler than End User Messaging Push |
| Firebase Cloud Messaging direct | FCM itself has no cost | Medium | Free, excellent Android support, can also route iOS through APNs configuration | Adds Google/Firebase control plane outside AWS; still needs app/device token setup | Good fallback, especially for Android-first |
| APNs direct | Apple does not charge separately for APNs sends | Low/Medium | Direct iOS path, no extra notification vendor | Requires APNs implementation, Apple developer setup, token management, and more custom server code | Avoid initially unless building an iOS-only app |
| Pushover | $4.99 one-time purchase per user platform for individual use | Low | Very fast to integrate, great for personal/internal alerts, no custom mobile app needed | External vendor, not AWS-native, less suitable for multi-user product push | Good short-term personal MVP fallback |
| ntfy | Free/public service or self-hosted open source | Low/Medium | Simple HTTP API, can self-host, no custom app needed | Public service dependency or self-hosting burden; not AWS-native unless self-hosted | Good dev/test fallback |
| OneSignal | Free to start; paid plans for advanced usage | Low | Polished dashboard and cross-platform tooling | Adds a third-party messaging platform and pricing model | Defer unless AWS path becomes painful |
| SMS via AWS End User Messaging | Pay per SMS/RCS segment, varies by country/carrier | Good | AWS-native and works without app install | Not push notification; can become expensive; phone-number compliance overhead | Avoid for initial product alerts |

## Implementation Notes For AWS End User Messaging Push

Add the following deployment pieces:

- AWS End User Messaging Push application for `priority-email`.
- APNs channel if supporting iOS.
- FCM channel if supporting Android.
- Runtime secret values:
  - `PUSH_PROVIDER=aws-end-user-messaging-push`
  - `PUSH_APPLICATION_ID`
  - `PUSH_CHANNELS_ENABLED`
  - APNs and/or FCM credential references
- DynamoDB table or app state field to store device tokens by user/device.
- IRSA policy permission for the service to send push messages through AWS End User Messaging Push.
- Metrics:
  - push sends attempted
  - push sends succeeded
  - push sends failed
  - invalid device tokens

## MVP Shortcut

If the first version is only for one person or a very small internal group, use this sequence:

1. Keep Slack posting as the default notification path because Slack mobile can already generate phone notifications.
2. Add Pushover or ntfy as a temporary direct-to-phone path if Slack notifications are not enough.
3. Move to AWS End User Messaging Push when there is a real app/device-token registration flow.

This keeps the initial deployment simple while preserving AWS End User Messaging Push as the production target.

## Sources

- AWS End User Messaging Push pricing: https://aws.amazon.com/end-user-messaging/pricing/
- AWS End User Messaging Push overview: https://docs.aws.amazon.com/push-notifications/latest/userguide/what-is-service.html
- AWS End User Messaging Push setup: https://docs.aws.amazon.com/push-notifications/latest/userguide/getting-started.html
- Amazon Pinpoint end-of-support notice: https://docs.aws.amazon.com/pinpoint/latest/userguide/migrate.html
- Amazon SNS pricing: https://aws.amazon.com/sns/pricing/
- Firebase Cloud Messaging pricing: https://firebase.google.com/products/cloud-messaging
- Pushover licensing: https://pushover.net/licensing
- ntfy overview: https://ntfy.sh/
- Apple Developer Program membership: https://developer.apple.com/support/compare-memberships/
