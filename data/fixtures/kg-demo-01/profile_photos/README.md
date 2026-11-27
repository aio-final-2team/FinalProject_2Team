# 가상 아이 프로필 사진 21장

아이 동그라미(관찰 기록·알림장 목록·우리 아이·동의 현황·앨범)에 보여 주는 얼굴 사진이에요. **실제 원아가 아니라 AI로 만든 가상 사진**이에요.

- 파일 이름 = 데모 아이 ID(`apps/api/app/mock/seed.py`의 `CHILDREN`). 예: `…000501.jpg` = 하늘이
- 출처: [`../../virtual_photos/faces`](../../virtual_photos/faces)의 정면 사진(`C4-NN_front.jpg`)을 320px로 줄였어요. 원래는 웹 `public/demo-faces`에 임시로 있던 파일이에요
- 쓰는 곳: 기동 시드(`db/seeds/photos.py`)가 데모 원과 사람별 QA 원 아이마다 `MEDIA_DIR/profiles/<아이 ID>.jpg`로 복사하고 `children.profile_photo_path`에 적어요. 화면은 아이 정보의 `profile_photo.file_url`(API 75)로 받아요
- 퇴소 작업을 거친 아이는 사진을 다시 넣지 않아요
