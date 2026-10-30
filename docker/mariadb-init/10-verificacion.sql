-- Se ejecuta solo la primera vez que se crea la base.
-- La verificación semanal de respaldos carga el último respaldo en esta base temporal, cuenta filas y la borra.
GRANT ALL PRIVILEGES ON `prospectos_verificacion`.* TO 'prospectos'@'%';
FLUSH PRIVILEGES;
