<template>
  <main class="login-page">
    <div class="login-shell">
      <section class="login-context" aria-label="平台简介">
        <div class="brand login-brand">
          <div class="brand-mark">SC</div>
          <div>
            <div class="brand-title">ANN 研究平台</div>
            <div class="brand-subtitle">单细胞检索工作台</div>
          </div>
        </div>

        <div class="login-introduction">
          <span class="login-eyebrow">科研数据工作台</span>
          <h1>让单细胞向量检索<br />保持清晰、可靠、可追踪</h1>
          <p>在统一界面中管理数据资源、验证 ANN 索引，并运行单数据集与跨数据集检索。</p>
        </div>

        <div class="login-capabilities">
          <div>
            <DatabaseOutlined />
            <span><strong>资源管理</strong><small>集中维护数据集与访问范围</small></span>
          </div>
          <div>
            <ExperimentOutlined />
            <span><strong>索引实验</strong><small>比较配置并保留评估依据</small></span>
          </div>
          <div>
            <DeploymentUnitOutlined />
            <span><strong>联合检索</strong><small>面向跨数据集研究场景</small></span>
          </div>
        </div>

        <div class="login-assurance"><SafetyCertificateOutlined />受控访问与操作记录</div>
      </section>

      <section class="login-panel" aria-label="账号访问">
        <div class="login-panel__head">
          <h2>{{ mode === 'login' ? '登录工作台' : '创建平台账号' }}</h2>
          <p>{{ mode === 'login' ? '使用平台账号继续访问研究资源。' : '创建账号后即可进入研究工作台。' }}</p>
        </div>

        <a-alert v-if="authError" class="login-alert" type="error" show-icon :message="authError" />

        <a-tabs v-model:active-key="mode" class="login-tabs" :animated="false" @change="authError = ''">
          <a-tab-pane key="login" tab="账号登录">
            <a-form :model="loginForm" layout="vertical" required-mark="optional" @finish="submitLogin">
              <a-form-item label="用户名" name="username" :rules="[{ required: true, whitespace: true, message: '请输入用户名' }]">
                <a-input v-model:value="loginForm.username" size="large" autocomplete="username" placeholder="请输入用户名">
                  <template #prefix><UserOutlined /></template>
                </a-input>
              </a-form-item>
              <a-form-item label="密码" name="password" :rules="[{ required: true, message: '请输入密码' }]">
                <a-input-password v-model:value="loginForm.password" size="large" autocomplete="current-password" placeholder="请输入密码">
                  <template #prefix><LockOutlined /></template>
                </a-input-password>
              </a-form-item>
              <a-button class="login-submit" type="primary" html-type="submit" size="large" block :loading="loading">进入平台</a-button>
            </a-form>
          </a-tab-pane>

          <a-tab-pane key="register" tab="创建账号">
            <a-form :model="registerForm" layout="vertical" required-mark="optional" @finish="submitRegister">
              <a-form-item label="用户名" name="username" :rules="[{ required: true, whitespace: true, message: '请输入用户名' }]">
                <a-input v-model:value="registerForm.username" size="large" autocomplete="username" placeholder="设置用户名">
                  <template #prefix><UserOutlined /></template>
                </a-input>
              </a-form-item>
              <a-form-item label="密码" name="password" :rules="[{ required: true, min: 4, message: '密码至少 4 位' }]">
                <a-input-password v-model:value="registerForm.password" size="large" autocomplete="new-password" placeholder="至少 4 个字符">
                  <template #prefix><LockOutlined /></template>
                </a-input-password>
              </a-form-item>
              <a-form-item label="确认密码" name="confirm" :rules="[{ required: true, message: '请再次输入密码' }]">
                <a-input-password v-model:value="registerForm.confirm" size="large" autocomplete="new-password" placeholder="再次输入密码">
                  <template #prefix><LockOutlined /></template>
                </a-input-password>
              </a-form-item>
              <a-button class="login-submit" type="primary" html-type="submit" size="large" block :loading="loading">创建并进入平台</a-button>
            </a-form>
          </a-tab-pane>
        </a-tabs>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  DatabaseOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const mode = ref(route.query.mode === "register" ? "register" : "login");
const loading = ref(false);
const authError = ref("");
const loginForm = reactive({ username: "", password: "" });
const registerForm = reactive({ username: "", password: "", confirm: "" });

function targetAfterLogin() {
  const next = route.query.next;
  return typeof next === "string" && next.startsWith("/") && !next.startsWith("//") ? next : "/overview";
}

async function submitLogin() {
  loading.value = true;
  authError.value = "";
  try {
    await auth.login(loginForm.username.trim(), loginForm.password);
    await router.replace(targetAfterLogin());
  } catch (error) {
    authError.value = (error as Error).message || "登录失败，请检查账号信息。";
  } finally {
    loading.value = false;
  }
}

async function submitRegister() {
  authError.value = "";
  if (registerForm.password !== registerForm.confirm) {
    authError.value = "两次输入的密码不一致。";
    return;
  }
  loading.value = true;
  try {
    await auth.register(registerForm.username.trim(), registerForm.password, registerForm.confirm);
    await router.replace("/overview");
  } catch (error) {
    authError.value = (error as Error).message || "账号创建失败，请稍后重试。";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  padding: 40px;
  place-items: center;
  background:
    linear-gradient(130deg, rgba(227, 236, 247, 0.82), rgba(244, 247, 250, 0.95) 48%, #eef2f6),
    #eef2f6;
}

.login-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) 430px;
  width: min(1040px, calc(100vw - 80px));
  min-height: 590px;
  overflow: hidden;
  border: 1px solid #dce3eb;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 22px 55px rgba(31, 52, 77, 0.11);
}

.login-context {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 34px 44px;
  overflow: hidden;
  background: linear-gradient(145deg, #123c67 0%, #174f83 55%, #1d6398 100%);
  color: #fff;
}

.login-context::after {
  position: absolute;
  right: -110px;
  bottom: -170px;
  width: 410px;
  height: 410px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 50%;
  box-shadow: 0 0 0 64px rgba(255, 255, 255, 0.025), 0 0 0 128px rgba(255, 255, 255, 0.018);
  content: "";
}

.login-brand {
  z-index: 1;
  padding: 0;
  border: 0;
}

.login-brand .brand-mark {
  background: #fff;
  color: #174f83;
}

.login-brand .brand-title {
  color: #fff;
}

.login-brand .brand-subtitle {
  color: rgba(255, 255, 255, 0.67);
}

.login-introduction {
  z-index: 1;
  margin-top: 72px;
}

.login-eyebrow {
  color: #9fc4e8;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.login-introduction h1 {
  margin: 13px 0 18px;
  color: #fff;
  font-size: 31px;
  line-height: 1.38;
  letter-spacing: -0.02em;
}

.login-introduction p {
  max-width: 500px;
  margin: 0;
  color: rgba(255, 255, 255, 0.72);
  font-size: 14px;
  line-height: 1.8;
}

.login-capabilities {
  z-index: 1;
  display: grid;
  gap: 14px;
  margin-top: 38px;
}

.login-capabilities > div {
  display: flex;
  align-items: center;
  gap: 13px;
}

.login-capabilities > div > .anticon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: #c8dff4;
}

.login-capabilities span {
  display: grid;
  gap: 2px;
}

.login-capabilities strong {
  font-size: 13px;
  font-weight: 600;
}

.login-capabilities small {
  color: rgba(255, 255, 255, 0.58);
  font-size: 12px;
}

.login-assurance {
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: auto;
  color: rgba(255, 255, 255, 0.58);
  font-size: 12px;
}

.login-panel {
  padding: 54px 44px 42px;
  background: #fff;
}

.login-panel__head h2 {
  margin: 0;
  color: #17243a;
  font-size: 23px;
}

.login-panel__head p {
  margin: 8px 0 24px;
  color: #77859a;
  font-size: 13px;
}

.login-alert {
  margin-bottom: 16px;
}

.login-tabs :deep(.ant-tabs-nav-list) {
  width: 100%;
}

.login-tabs :deep(.ant-tabs-tab) {
  flex: 1;
  justify-content: center;
}

.login-tabs :deep(.ant-tabs-content) {
  padding-top: 8px;
}

.login-tabs :deep(.ant-input-affix-wrapper) {
  padding-inline: 12px;
}

.login-tabs :deep(.ant-input-prefix) {
  margin-inline-end: 9px;
  color: #8b97a8;
}

.login-submit {
  margin-top: 4px;
  font-weight: 600;
}
</style>
