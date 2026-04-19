# 🎓 Local AI Instruction (교육용 AI 플랫폼)

로컬 LLM(LM Studio) 및 클라우드 AI(Gemini, OpenAI, Claude)를 활용하여 교육 자료 분석, 문제 생성, 인터랙티브 퀴즈 풀이, 오답노트 관리를 수행하는 **올인원 에듀테크 플랫폼**입니다.

---

<img width="1728" height="1117" alt="Main UI" src="https://github.com/user-attachments/assets/75704484-b69c-41c2-b9da-9a46a6be70eb" />

---

## 🌟 주요 핵심 기능

### 1. 🎯 지능형 문항 생성 및 인터랙티브 풀이 (Smart Quiz System)
- **JSON 기반 정밀 파싱**: AI 응답을 JSON 구조로 강제하여 파싱 에러를 최소화하고 데이터 신뢰성을 확보했습니다.
- **다양한 문항 유형**: 4지선다, 단답형, 서술형, T/F, 빈칸 채우기 등 교육 목적에 맞는 다양한 유형을 생성합니다.
- **실시간 풀이 환경**: 생성된 퀴즈를 앱 내에서 즉시 풀고 채점 결과를 확인할 수 있는 전용 UI를 제공합니다.

### 2. 📓 스마트 오답노트 & 과목 자동 추론
- **오답노트 분류 관리**: 틀린 문제를 과목별로 자동 분류하거나 수동으로 필터링하여 복습할 수 있습니다.
- **자동 과목 추론 (Subject Inference)**: 별도의 설정 없이도 AI가 문제의 문맥을 파악해 국어, 수학, 영어 등 적절한 카테고리를 판단하여 저장합니다.
- **지속적 학습 피드백**: 저장된 오답은 언제든 다시 확인하고 해설을 복습할 수 있습니다.

### 3. 📄 고해상도 PDF 및 멀티미디어 분석
- **Hybrid Extraction**: PyMuPDF와 PyPDF를 병행 사용하여 고난도 레이아웃의 PDF에서도 텍스트와 이미지를 완벽하게 추출합니다.
- **Vision 지원**: 이미지 파일을 분석하여 텍스트로 변환하거나 문제를 풀이하는 시각 분석 기능을 탑재하고 있습니다.

### 4. 👩‍🏫 전역 사용자 페르소나 (Global AI Persona)
- **교육자용 모드**: 교수법 조언, 상세 채점 기준, 교육적 피드백 제공.
- **수강생용 모드**: 쉬운 개념 설명, 메타인지 가이드, 단계별 힌트 제공.

---

## 🏗 시스템 아키텍처 (Modular Architecture)

본 프로젝트는 유지보수성과 확장성을 위해 기능별로 독립된 모듈 구조를 채택하고 있습니다.

### 📦 `app/pages/` - 모듈형 UI 레이어
- **`_quiz_generator.py`**: 퀴즈 생성 및 풀이 로직 엔진.
- **`_wrong_notes.py`**: 과목별 오답 관리 및 필터링 시스템.
- **`_lesson_plan.py`**: 교사용 수업 지도안 및 평가 계획서 생성기.
- **`_pdf_analyzer.py`**: 대용량 문서 분석 및 요약.
*외 7종의 독립 기능 모듈*

### 📦 `src/` - 핵심 비즈니스 로직
- **`app_utils.py`**: PDF 이미지 추출, JSON 수선(json-repair), LaTeX 수식 정규화 등 핵심 유틸리티.
- **`models.py`**: OpenAI, Gemini, Claude 및 로컬 LLM 통신 표준화 계층.
- **`config.py`**: `SUBJECT_LIST` 및 전역 파라미터 관리.

---

## 🔑 운영 모델 (BYOK - Bring Your Own Key)

본 플랫폼은 사용자의 프라이버시와 투명한 비용 관리를 위해 **BYOK 모델**로 운영됩니다.

- **개인 키 사용**: 사용자가 보유한 개별 API Key(OpenAI, Gemini 등)를 직접 활용하여 API 비용을 투명하게 관리합니다.
- **로컬 LLM 연동**: 보안이 중요한 자료는 LM Studio, Ollama 등을 통해 외부 유출 없이 로컬 환경에서만 처리할 수 있습니다.

---

## 🛠 기술 스택
- **Language**: Python 3.10+
- **Frontend**: Streamlit (with Custom CSS / Glassmorphism)
- **AI Backend**: OpenAI SDK, Google Generative AI, Anthropic API
- **Document Engine**: PyMuPDF, PyPDF, WeasyPrint
- **Logic Support**: json-repair (Robust Parser), Matplotlib (Formula Rendering)

---

## 🚀 시작하기
1. 레포지토리를 클론합니다.
2. `pip install -r requirements.txt`로 필요한 의존성을 설치합니다.
3. `streamlit run app/main.py` 명령어로 플랫폼을 실행합니다.
