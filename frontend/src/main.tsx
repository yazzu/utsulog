import { AwsRum, type AwsRumConfig } from 'aws-rum-web';
try {
  const config: AwsRumConfig = {
    sessionSampleRate: 1,
    identityPoolId: "ap-northeast-1:69e2fb72-8a05-42a4-83f1-ecf12ac00463",
    endpoint: "https://dataplane.rum.ap-northeast-1.amazonaws.com",
    telemetries: ["performance", "errors", "http"],
    allowCookies: true,
    enableXRay: false,
    signing: true // If you have a public resource policy and wish to send unsigned requests please set this to false
  };

  const APPLICATION_ID: string = 'd37a8429-dd91-4dd3-941f-1d30fcd8188d';
  const APPLICATION_VERSION: string = '1.0.0';
  const APPLICATION_REGION: string = 'ap-northeast-1';

  new AwsRum(
    APPLICATION_ID,
    APPLICATION_VERSION,
    APPLICATION_REGION,
    config
  );
} catch (error) {
  // Ignore errors thrown during CloudWatch RUM web client initialization
}

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
