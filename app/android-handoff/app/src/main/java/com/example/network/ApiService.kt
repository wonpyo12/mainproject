package com.example.network

import retrofit2.http.*

interface ApiService {

    // [MySQL] 회원가입
    @POST("api/auth/register")
    suspend fun register(@Body request: RegisterRequest): RegisterResponse

    // [MySQL] 로그인 → JWT 발급
    @POST("api/auth/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    // [Redis] QR 세션 생성 (TTL 180초)
    @GET("api/auth/qr")
    suspend fun generateQR(
        @Header("Authorization") authHeader: String,
    ): QrResponse

    // [Redis → MySQL] 결제 완료 및 주문 이력 저장
    @POST("api/orders/complete")
    suspend fun completeOrder(
        @Header("Authorization") authHeader: String,
        @Body request: CompleteOrderRequest,
    ): CompleteOrderResponse

    // [MySQL] 유저 주문 이력 조회
    @GET("api/orders/history")
    suspend fun getOrderHistory(
        @Header("Authorization") authHeader: String,
    ): OrderHistoryResponse

    // [로봇] 정지 — 그 자리 래치 정지(HALT)
    @POST("api/robot/stop")
    suspend fun stopRobot(
        @Header("Authorization") authHeader: String,
        @Body request: RobotCommandRequest,
    ): ApiResponse

    // [로봇] 추종 재개 — 정지 해제(RESUME)
    @POST("api/robot/resume")
    suspend fun resumeRobot(
        @Header("Authorization") authHeader: String,
        @Body request: RobotCommandRequest,
    ): ApiResponse
}
