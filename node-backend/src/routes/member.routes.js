const express = require('express');
const router = express.Router();
const memberController = require('../controllers/member.controller');
// const { authenticateToken } = require('../middleware/auth'); // 관리자 인증 필요 시 활성화

// [MySQL] 회원 목록 조회 - 페이징, 검색, 타입 필터
router.get('/', memberController.getMembers);

// [MySQL] 특정 회원 상세 조회
router.get('/:id', memberController.getMember);

// [MySQL] 회원 정보 수정
router.patch('/:id', memberController.updateMember);

// [MySQL] 회원 삭제
router.delete('/:id', memberController.deleteMember);

module.exports = router;
