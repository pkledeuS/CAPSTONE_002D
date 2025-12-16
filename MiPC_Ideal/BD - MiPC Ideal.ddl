-- Generado por Oracle SQL Developer Data Modeler 24.3.1.351.0831
--   en:        2025-11-15 10:07:33 CLST
--   sitio:      Oracle Database 21c
--   tipo:      Oracle Database 21c



-- predefined type, no DDL - MDSYS.SDO_GEOMETRY

-- predefined type, no DDL - XMLTYPE

CREATE SEQUENCE auth_user_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE categoria_producto_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE especificacion_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE marca_producto_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE preferencia_usuario_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE prod_cat_extra_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE product_reference_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE product_review_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE producto_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE producto_visto_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE productos_favoritos_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE profile_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE reference_visit_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE reporte_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE tipo_producto_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE SEQUENCE view_stat_seq 
    START WITH 1 
    INCREMENT BY 1 
    NOCACHE 
;

CREATE TABLE auth_user 
    ( 
     id           NUMBER (10)  NOT NULL , 
     username     VARCHAR2 (150)  NOT NULL , 
     email        VARCHAR2 (254)  NOT NULL , 
     password     VARCHAR2 (128)  NOT NULL , 
     first_name   VARCHAR2 (150) , 
     last_name    VARCHAR2 (150) , 
     is_active    NUMBER (1) DEFAULT 1 , 
     is_staff     NUMBER (1) DEFAULT 0 , 
     is_superuser NUMBER (1) DEFAULT 0 , 
     date_joined  TIMESTAMP DEFAULT CURRENT_TIMESTAMP , 
     last_login   TIMESTAMP 
    ) 
    LOGGING 
;

ALTER TABLE auth_user 
    ADD CONSTRAINT pk_auth_user PRIMARY KEY ( id ) ;

ALTER TABLE auth_user 
    ADD CONSTRAINT uk_auth_user_email UNIQUE ( email ) ;

ALTER TABLE auth_user 
    ADD CONSTRAINT uk_auth_user_username UNIQUE ( username ) ;

CREATE TABLE CategoriaProducto 
    ( 
     id                    NUMBER (10)  NOT NULL , 
     nombre_categoria      VARCHAR2 (100)  NOT NULL , 
     descripcion_categoria CLOB , 
     imagen_categoria      VARCHAR2 (255) , 
     banner_categoria      VARCHAR2 (255) 
    ) 
    LOGGING 
;

ALTER TABLE CategoriaProducto 
    ADD CONSTRAINT pk_categoria_producto PRIMARY KEY ( id ) ;

ALTER TABLE CategoriaProducto 
    ADD CONSTRAINT uk_categoria_nombre UNIQUE ( nombre_categoria ) ;

CREATE TABLE EspecificacionProducto 
    ( 
     id                    NUMBER (10)  NOT NULL , 
     producto_id           NUMBER (10)  NOT NULL , 
     nombre_especificacion VARCHAR2 (100)  NOT NULL , 
     valor_especificacion  VARCHAR2 (200) 
    ) 
    LOGGING 
;
CREATE INDEX idx_espec_producto ON EspecificacionProducto 
    ( 
     producto_id ASC 
    ) 
;

ALTER TABLE EspecificacionProducto 
    ADD CONSTRAINT pk_especificacion PRIMARY KEY ( id ) ;

CREATE TABLE MarcaProducto 
    ( 
     id           NUMBER (10)  NOT NULL , 
     nombre_marca VARCHAR2 (100)  NOT NULL 
    ) 
    LOGGING 
;

ALTER TABLE MarcaProducto 
    ADD CONSTRAINT pk_marca_producto PRIMARY KEY ( id ) ;

ALTER TABLE MarcaProducto 
    ADD CONSTRAINT uk_marca_nombre UNIQUE ( nombre_marca ) ;

CREATE TABLE PreferenciaUsuario 
    ( 
     id               NUMBER (10)  NOT NULL , 
     usuario_id       NUMBER (10)  NOT NULL , 
     categoria_id     NUMBER (10) , 
     tipo_producto_id NUMBER (10) 
    ) 
    LOGGING 
;
CREATE INDEX idx_preferencia_user ON PreferenciaUsuario 
    ( 
     usuario_id ASC 
    ) 
;

ALTER TABLE PreferenciaUsuario 
    ADD CONSTRAINT pk_preferencia_usuario PRIMARY KEY ( id ) ;

CREATE TABLE Producto 
    ( 
     id                    NUMBER (10)  NOT NULL , 
     nombre_producto       VARCHAR2 (100)  NOT NULL , 
     descripcion_producto  CLOB , 
     modelo_producto       VARCHAR2 (100) , 
     imagen_producto       VARCHAR2 (255) , 
     fecha_creacion        TIMESTAMP DEFAULT CURRENT_TIMESTAMP , 
     marca_producto_id     NUMBER (10)  NOT NULL , 
     categoria_producto_id NUMBER (10)  NOT NULL , 
     tipo_producto_id      NUMBER (10)  NOT NULL , 
     vistas                NUMBER (10) DEFAULT 0 , 
     is_active             NUMBER (1) DEFAULT 1 
    ) 
    LOGGING 
;
CREATE INDEX idx_producto_marca ON Producto 
    ( 
     marca_producto_id ASC 
    ) 
;
CREATE INDEX idx_producto_categoria ON Producto 
    ( 
     categoria_producto_id ASC 
    ) 
;
CREATE INDEX idx_producto_tipo ON Producto 
    ( 
     tipo_producto_id ASC 
    ) 
;
CREATE INDEX idx_producto_active ON Producto 
    ( 
     is_active ASC 
    ) 
;

ALTER TABLE Producto 
    ADD CONSTRAINT pk_producto PRIMARY KEY ( id ) ;

CREATE TABLE Producto_CategoriaExtra 
    ( 
     id           NUMBER (10)  NOT NULL , 
     producto_id  NUMBER (10)  NOT NULL , 
     categoria_id NUMBER (10)  NOT NULL 
    ) 
    LOGGING 
;

ALTER TABLE Producto_CategoriaExtra 
    ADD CONSTRAINT pk_producto_cat_extra PRIMARY KEY ( id ) ;

ALTER TABLE Producto_CategoriaExtra 
    ADD CONSTRAINT uk_prod_cat_extra UNIQUE ( producto_id , categoria_id ) ;

CREATE TABLE ProductosFavoritos 
    ( 
     id             NUMBER (10)  NOT NULL , 
     usuario_id     NUMBER (10)  NOT NULL , 
     producto_id    NUMBER (10)  NOT NULL , 
     fecha_agregado TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
    ) 
    LOGGING 
;
CREATE INDEX idx_favoritos_user ON ProductosFavoritos 
    ( 
     usuario_id ASC 
    ) 
;
CREATE INDEX idx_favoritos_producto ON ProductosFavoritos 
    ( 
     producto_id ASC 
    ) 
;

ALTER TABLE ProductosFavoritos 
    ADD CONSTRAINT pk_productos_favoritos PRIMARY KEY ( id ) ;

ALTER TABLE ProductosFavoritos 
    ADD CONSTRAINT uk_favoritos UNIQUE ( usuario_id , producto_id ) ;

CREATE TABLE ProductoVisto 
    ( 
     id          NUMBER (10)  NOT NULL , 
     usuario_id  NUMBER (10) , 
     producto_id NUMBER (10)  NOT NULL , 
     fecha_visto TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
    ) 
    LOGGING 
;
CREATE INDEX idx_visto_usuario ON ProductoVisto 
    ( 
     usuario_id ASC 
    ) 
;
CREATE INDEX idx_visto_producto ON ProductoVisto 
    ( 
     producto_id ASC 
    ) 
;
CREATE INDEX idx_visto_fecha ON ProductoVisto 
    ( 
     fecha_visto ASC 
    ) 
;

ALTER TABLE ProductoVisto 
    ADD CONSTRAINT pk_producto_visto PRIMARY KEY ( id ) ;

CREATE TABLE ProductReference 
    ( 
     id            NUMBER (10)  NOT NULL , 
     producto_id   NUMBER (10)  NOT NULL , 
     nombre_fuente VARCHAR2 (120)  NOT NULL , 
     url_fuente    VARCHAR2 (300) , 
     precio        NUMBER (12,2)  NOT NULL , 
     stock         NUMBER (10) DEFAULT 0 , 
     nota          VARCHAR2 (200) , 
     actualizado   TIMESTAMP DEFAULT CURRENT_TIMESTAMP , 
     creado        TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
    ) 
    LOGGING 
;
CREATE INDEX idx_reference_producto ON ProductReference 
    ( 
     producto_id ASC 
    ) 
;
CREATE INDEX idx_reference_precio ON ProductReference 
    ( 
     precio ASC 
    ) 
;

ALTER TABLE ProductReference 
    ADD CONSTRAINT chk_reference_precio 
    CHECK (precio >= 0)
;


ALTER TABLE ProductReference 
    ADD CONSTRAINT chk_reference_stock 
    CHECK (stock >= 0)
;
ALTER TABLE ProductReference 
    ADD CONSTRAINT pk_product_reference PRIMARY KEY ( id ) ;

CREATE TABLE ProductReview 
    ( 
     id          NUMBER (10)  NOT NULL , 
     producto_id NUMBER (10)  NOT NULL , 
     user_id     NUMBER (10)  NOT NULL , 
     rating      NUMBER (1)  NOT NULL , 
     "comment"   CLOB , 
     created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP , 
     updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
    ) 
    LOGGING 
;
CREATE INDEX idx_review_producto ON ProductReview 
    ( 
     producto_id ASC 
    ) 
;
CREATE INDEX idx_review_user ON ProductReview 
    ( 
     user_id ASC 
    ) 
;
CREATE INDEX idx_review_created ON ProductReview 
    ( 
     created_at ASC 
    ) 
;

ALTER TABLE ProductReview 
    ADD CONSTRAINT chk_review_rating 
    CHECK (rating BETWEEN 1 AND 5)
;
ALTER TABLE ProductReview 
    ADD CONSTRAINT pk_product_review PRIMARY KEY ( id ) ;

ALTER TABLE ProductReview 
    ADD CONSTRAINT uk_review UNIQUE ( user_id , producto_id ) ;

CREATE TABLE Profile 
    ( 
     id                      NUMBER (10)  NOT NULL , 
     user_id                 NUMBER (10)  NOT NULL , 
     profile_type            VARCHAR2 (50) DEFAULT 'usuario'  NOT NULL , 
     is_active               NUMBER (1) DEFAULT 1 , 
     preferred_budget_min    NUMBER (10) , 
     preferred_budget_max    NUMBER (10) , 
     preference_notes        CLOB , 
     preferred_budget_manual NUMBER (1) DEFAULT 0 
    ) 
    LOGGING 
;

ALTER TABLE Profile 
    ADD CONSTRAINT chk_profile_type 
    CHECK (profile_type IN ('usuario', 'admin'))
;
ALTER TABLE Profile 
    ADD CONSTRAINT pk_profile PRIMARY KEY ( id ) ;

ALTER TABLE Profile 
    ADD CONSTRAINT uk_profile_user UNIQUE ( user_id ) ;

CREATE TABLE ReferenceVisit 
    ( 
     id            NUMBER (10)  NOT NULL , 
     referencia_id NUMBER (10)  NOT NULL , 
     usuario_id    NUMBER (10) , 
     clicked_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
    ) 
    LOGGING 
;
CREATE INDEX idx_visit_reference ON ReferenceVisit 
    ( 
     referencia_id ASC 
    ) 
;
CREATE INDEX idx_visit_user ON ReferenceVisit 
    ( 
     usuario_id ASC 
    ) 
;

ALTER TABLE ReferenceVisit 
    ADD CONSTRAINT pk_reference_visit PRIMARY KEY ( id ) ;

CREATE TABLE Reporte 
    ( 
     id                     NUMBER (10)  NOT NULL , 
     target_type            VARCHAR2 (20) DEFAULT 'producto'  NOT NULL , 
     producto_id            NUMBER (10) , 
     reporter_id            NUMBER (10) , 
     motivo                 VARCHAR2 (50)  NOT NULL , 
     detalle                CLOB , 
     created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP , 
     estado                 VARCHAR2 (20) DEFAULT 'abierto' , 
     accion_admin           CLOB , 
     fecha_accion           TIMESTAMP , 
     admin_actor_id         NUMBER (10) , 
     producto_deshabilitado NUMBER (1) DEFAULT 0 , 
     notificacion_leida     NUMBER (1) DEFAULT 0 
    ) 
    LOGGING 
;
CREATE INDEX idx_reporte_producto ON Reporte 
    ( 
     producto_id ASC 
    ) 
;
CREATE INDEX idx_reporte_reporter ON Reporte 
    ( 
     reporter_id ASC 
    ) 
;
CREATE INDEX idx_reporte_estado ON Reporte 
    ( 
     estado ASC 
    ) 
;
CREATE INDEX idx_reporte_created ON Reporte 
    ( 
     created_at ASC 
    ) 
;

ALTER TABLE Reporte 
    ADD CONSTRAINT chk_reporte_estado 
    CHECK (estado IN ('abierto', 'pendiente', 'resuelto'))
;


ALTER TABLE Reporte 
    ADD CONSTRAINT chk_reporte_target 
    CHECK (target_type = 'producto')
;
ALTER TABLE Reporte 
    ADD CONSTRAINT pk_reporte PRIMARY KEY ( id ) ;

CREATE TABLE TipoProducto 
    ( 
     id          NUMBER (10)  NOT NULL , 
     nombre_tipo VARCHAR2 (100)  NOT NULL 
    ) 
    LOGGING 
;

ALTER TABLE TipoProducto 
    ADD CONSTRAINT pk_tipo_producto PRIMARY KEY ( id ) ;

ALTER TABLE TipoProducto 
    ADD CONSTRAINT uk_tipo_nombre UNIQUE ( nombre_tipo ) ;

CREATE TABLE UserViewStat 
    ( 
     id         NUMBER (10)  NOT NULL , 
     usuario_id NUMBER (10)  NOT NULL , 
     metric     VARCHAR2 (20)  NOT NULL , 
     key        VARCHAR2 (120)  NOT NULL , 
     count      NUMBER (10) DEFAULT 0 , 
     last_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
    ) 
    LOGGING 
;
CREATE INDEX idx_view_stat_user_metric ON UserViewStat 
    ( 
     usuario_id ASC , 
     metric ASC 
    ) 
;

ALTER TABLE UserViewStat 
    ADD CONSTRAINT chk_view_metric 
    CHECK (metric IN ('brand','category','type','price_band'))
;
ALTER TABLE UserViewStat 
    ADD CONSTRAINT pk_view_stat PRIMARY KEY ( id ) ;

ALTER TABLE UserViewStat 
    ADD CONSTRAINT uk_view_stat UNIQUE ( usuario_id , metric , key ) ;

ALTER TABLE EspecificacionProducto 
    ADD CONSTRAINT fk_espec_producto FOREIGN KEY 
    ( 
     producto_id
    ) 
    REFERENCES Producto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ProductosFavoritos 
    ADD CONSTRAINT fk_favoritos_producto FOREIGN KEY 
    ( 
     producto_id
    ) 
    REFERENCES Producto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ProductosFavoritos 
    ADD CONSTRAINT fk_favoritos_usuario FOREIGN KEY 
    ( 
     usuario_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Producto_CategoriaExtra 
    ADD CONSTRAINT fk_pce_categoria FOREIGN KEY 
    ( 
     categoria_id
    ) 
    REFERENCES CategoriaProducto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Producto_CategoriaExtra 
    ADD CONSTRAINT fk_pce_producto FOREIGN KEY 
    ( 
     producto_id
    ) 
    REFERENCES Producto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE PreferenciaUsuario 
    ADD CONSTRAINT fk_preferencia_categoria FOREIGN KEY 
    ( 
     categoria_id
    ) 
    REFERENCES CategoriaProducto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE PreferenciaUsuario 
    ADD CONSTRAINT fk_preferencia_tipo FOREIGN KEY 
    ( 
     tipo_producto_id
    ) 
    REFERENCES TipoProducto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE PreferenciaUsuario 
    ADD CONSTRAINT fk_preferencia_usuario FOREIGN KEY 
    ( 
     usuario_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Producto 
    ADD CONSTRAINT fk_producto_categoria FOREIGN KEY 
    ( 
     categoria_producto_id
    ) 
    REFERENCES CategoriaProducto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Producto 
    ADD CONSTRAINT fk_producto_marca FOREIGN KEY 
    ( 
     marca_producto_id
    ) 
    REFERENCES MarcaProducto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Producto 
    ADD CONSTRAINT fk_producto_tipo FOREIGN KEY 
    ( 
     tipo_producto_id
    ) 
    REFERENCES TipoProducto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Profile 
    ADD CONSTRAINT fk_profile_user FOREIGN KEY 
    ( 
     user_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ProductReference 
    ADD CONSTRAINT fk_reference_producto FOREIGN KEY 
    ( 
     producto_id
    ) 
    REFERENCES Producto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Reporte 
    ADD CONSTRAINT fk_reporte_admin FOREIGN KEY 
    ( 
     admin_actor_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Reporte 
    ADD CONSTRAINT fk_reporte_producto FOREIGN KEY 
    ( 
     producto_id
    ) 
    REFERENCES Producto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE Reporte 
    ADD CONSTRAINT fk_reporte_reporter FOREIGN KEY 
    ( 
     reporter_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ProductReview 
    ADD CONSTRAINT fk_review_producto FOREIGN KEY 
    ( 
     producto_id
    ) 
    REFERENCES Producto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ProductReview 
    ADD CONSTRAINT fk_review_user FOREIGN KEY 
    ( 
     user_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE UserViewStat 
    ADD CONSTRAINT fk_view_stat_user FOREIGN KEY 
    ( 
     usuario_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ReferenceVisit 
    ADD CONSTRAINT fk_visit_reference FOREIGN KEY 
    ( 
     referencia_id
    ) 
    REFERENCES ProductReference 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ReferenceVisit 
    ADD CONSTRAINT fk_visit_user FOREIGN KEY 
    ( 
     usuario_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ProductoVisto 
    ADD CONSTRAINT fk_visto_producto FOREIGN KEY 
    ( 
     producto_id
    ) 
    REFERENCES Producto 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;

ALTER TABLE ProductoVisto 
    ADD CONSTRAINT fk_visto_usuario FOREIGN KEY 
    ( 
     usuario_id
    ) 
    REFERENCES auth_user 
    ( 
     id
    ) 
    NOT DEFERRABLE 
;



-- Informe de Resumen de Oracle SQL Developer Data Modeler: 
-- 
-- CREATE TABLE                            16
-- CREATE INDEX                            23
-- ALTER TABLE                             56
-- CREATE VIEW                              0
-- ALTER VIEW                               0
-- CREATE PACKAGE                           0
-- CREATE PACKAGE BODY                      0
-- CREATE PROCEDURE                         0
-- CREATE FUNCTION                          0
-- CREATE TRIGGER                           0
-- ALTER TRIGGER                            0
-- CREATE COLLECTION TYPE                   0
-- CREATE STRUCTURED TYPE                   0
-- CREATE STRUCTURED TYPE BODY              0
-- CREATE CLUSTER                           0
-- CREATE CONTEXT                           0
-- CREATE DATABASE                          0
-- CREATE DIMENSION                         0
-- CREATE DIRECTORY                         0
-- CREATE DISK GROUP                        0
-- CREATE ROLE                              0
-- CREATE ROLLBACK SEGMENT                  0
-- CREATE SEQUENCE                         16
-- CREATE MATERIALIZED VIEW                 0
-- CREATE MATERIALIZED VIEW LOG             0
-- CREATE SYNONYM                           0
-- CREATE TABLESPACE                        0
-- CREATE USER                              0
-- 
-- DROP TABLESPACE                          0
-- DROP DATABASE                            0
-- 
-- REDACTION POLICY                         0
-- 
-- ORDS DROP SCHEMA                         0
-- ORDS ENABLE SCHEMA                       0
-- ORDS ENABLE OBJECT                       0
-- 
-- ERRORS                                   0
-- WARNINGS                                 0
